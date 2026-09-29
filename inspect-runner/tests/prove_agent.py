"""Run a real agent binary against scripted, key-free model replies."""
import argparse
import base64
import json
import os
import re
import time
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from inspect_ai import eval
from inspect_ai.model import ModelOutput, get_model

from support import build_task, fixture_config, valid_search_result
from ethevals.agents import CodexModel
from ethevals.loader import load_eval
from ethevals.rows import export_rows
from ethevals.preparation import build_images, prepare_compose


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("answer", choices=["reference", "empty"])
    parser.add_argument("--model", choices=["opus", "codex", "kimi", "glm"], default="opus")
    parser.add_argument("--eval", default="evals/building/erc20-points-token")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--exa-canary", action="store_true")
    args = parser.parse_args()
    if not args.exa_canary:
        assert not os.environ.get("EXA_API_KEY"), "Strip EXA_API_KEY before the keyless search proof."
    if args.exa_canary:
        import ethevals.search as search
        os.environ["EXA_API_KEY"] = "inert-offline-exa-canary"

        async def offline_exa(url, name, arguments, key):
            assert key == "inert-offline-exa-canary"
            import hashlib
            from inspect_ai.util import sandbox
            from ethevals.sandboxes import runner_exec
            # Pass a digest, never the canary itself, into the live agent container.
            scan = """
const fs = require("fs"), crypto = require("crypto");
const matches = []; let files = 0, environments = 0;
function check(path) {
  let fd;
  try {
    fd = fs.openSync(path, "r");
    let tail = Buffer.alloc(0), block = Buffer.alloc(1048576), length;
    while ((length = fs.readSync(fd, block)) > 0) {
      const data = Buffer.concat([tail, block.subarray(0, length)]);
      let start = -1;
      while ((start = data.indexOf("inert-", start + 1)) >= 0) {
        if (crypto.createHash("sha256").update(data.subarray(start, start + SIZE)).digest("hex") === DIGEST)
          matches.push(path);
      }
      tail = Buffer.from(data.subarray(-SIZE));
    }
    files++;
  } catch {} finally { if (fd !== undefined) fs.closeSync(fd); }
}
function walk(root) {
  let names;
  try { names = fs.readdirSync(root, {withFileTypes: true}); } catch { return; }
  for (const name of names) {
    const path = root === "/" ? "/" + name.name : root + "/" + name.name;
    if (["/proc", "/sys", "/dev"].includes(path)) continue;
    if (name.isDirectory()) walk(path);
    else if (name.isFile()) check(path);
  }
}
walk("/");
for (const name of fs.readdirSync("/proc")) {
  if (/^[0-9]+$/.test(name)) { environments++; check("/proc/" + name + "/environ"); }
}
console.log(JSON.stringify({matches, files, environments}));
"""
            scan = "const SIZE=" + str(len(key)) + ", DIGEST=" + json.dumps(hashlib.sha256(key.encode()).hexdigest()) + ";\n" + scan
            result = await runner_exec(sandbox(), ["/usr/local/bin/node", "-e", scan], user="root", timeout=90)
            assert result.success, result.stderr
            scanned = json.loads(result.stdout)
            assert scanned["matches"] == [] and scanned["files"] > 100 and scanned["environments"] > 1, scanned
            print(json.dumps({"container_canary_scan": scanned}), flush=True)
            return {"content": [{"type": "text", "text": "Title: ERC-20\nURL: https://ethereum.org\nContent: Test search. " + key}]}

        search.exa_request = offline_exa
    assert not any(os.environ.get(name) for name in ("OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_AUTH_TOKEN")), "Strip provider credentials before this proof."
    config = fixture_config()
    config.agents[args.model].model = "mockllm/model"
    config.grader.model = "mockllm/model"
    evaluation = load_eval(Path(args.eval), config)
    build_images()
    compose = prepare_compose(evaluation, args.output)
    task = build_task(evaluation, config, args.model, "internet", None, 1, compose)
    task.metadata.update(free_check=True, cost_source="mock", grader_cost_source="mock")
    calls = 0
    tool_names = set()
    harness = config.agents[args.model].harness
    cli_identity = config.agents[args.model].agent_model_config
    requests = []
    search_ok = False
    search_call = 2 if harness == "codex_cli" else 1

    def capture(original):
        def record(data):
            requests.append(data)
            with (args.output / "cli-requests.jsonl").open("a") as stream:
                stream.write(json.dumps(data) + "\n")
            return original(data)
        return record

    def reply(messages, tools, tool_choice, config):
        nonlocal calls, search_ok
        calls += 1
        tool_names.update(tool.name for tool in tools)
        if harness == "codex_cli":
            for message in messages:
                if message.role == "tool":
                    tool_names.update(re.findall(r'"([A-Za-z_]+)"', message.text))
        print(json.dumps({"bridge_call": calls, "tools": sorted(tool_names), "effort": config.reasoning_effort}), flush=True)
        if harness == "opencode":
            assert requests[-1]["model"] == cli_identity.removeprefix("openrouter/"), requests[-1]["model"]
            system = "\n".join(message.text for message in messages if message.role == "system")
            expected = "interactive general AI agent" if "kimi" in cli_identity else "interactive CLI tool"
            assert expected in system, system
            assert "claude" not in system.lower(), system
            assert cli_identity in system, system
        if harness == "codex_cli" and calls == 1:
            return ModelOutput.for_tool_call("mockllm/model", "exec", {
                "input": "text(ALL_TOOLS.map(tool => tool.name));",
            })
        if calls == search_call:
            arguments = {"query": "site:ethereum.org ERC-20 token standard", "numResults": 1,
                         "objective": "Find the official ERC-20 token standard and its methods."}
            if harness == "codex_cli":
                name, arguments = "exec", {"input": "text(await tools.mcp__exa__web_search_exa(" + json.dumps(arguments) + "));"}
            else:
                name = next(name for name in tool_names if "web_search_exa" in name)
            return ModelOutput.for_tool_call("mockllm/model", name, arguments)
        if calls == search_call + 1:
            result = next(message for message in reversed(messages) if message.role == "tool")
            assert not result.error, result
            assert valid_search_result(result.text), result.text
            assert "ERC" in result.text or "token" in result.text.lower(), result.text
            search_ok = True
            print(json.dumps({"exa_search": "passed", "result": result.text}), flush=True)
        if evaluation.declaration.type == "quiz":
            return ModelOutput.from_content("mockllm/model", "ANSWER: C" if evaluation.declaration.choices else "8004")
        if calls == search_call + 1 and args.answer == "reference":
            if evaluation.declaration.type == "act":
                solution = evaluation.files["scorer/solution/run.sh"]
                encoded = base64.b64encode(solution).decode()
                command = ("test ! -e /workspace/scorer && "
                           f"printf '%s' '{encoded}' | base64 -d > /workspace/run.sh && bash /workspace/run.sh")
                return ModelOutput.for_tool_call("mockllm/model", "Bash", {"command": command, "description": "Read decimals and sign the transfer"})
            solution = (evaluation.folder / "scorer/solution/src/BuilderPoints.sol").read_bytes()
            encoded = base64.b64encode(solution).decode()
            command = (
                "test ! -e /workspace/scorer && test ! -e /workspace/test/BuilderPoints.t.sol && "
                "test ! -e /workspace/rubric.md && "
                f"printf '%s' '{encoded}' | base64 -d > /workspace/src/BuilderPoints.sol && forge build"
            )
            if harness == "codex_cli":
                name, arguments = "exec", {"input": "text(await tools.exec_command(" + json.dumps({"cmd": command}) + "));"}
            else:
                name = "Bash" if harness == "claude_code" else "bash"
                arguments = {"command": command, "description": "Write the requested token"}
            return ModelOutput.for_tool_call("mockllm/model", name, arguments)
        return ModelOutput.from_content("mockllm/model", "Done.")

    def grade(messages, tools, tool_choice, config):
        evidence = json.loads(messages[1].text)
        assert "src/BuilderPoints.sol" in evidence
        assert "lib/openzeppelin-contracts/contracts/token/ERC20/ERC20.sol" not in evidence
        passed = args.answer == "reference"
        return ModelOutput.from_content("mockllm/model", json.dumps({
            "passed": passed,
            "reason": "The submitted token uses OpenZeppelin without holder controls." if passed else "The workspace contains an empty contract.",
        }))

    task.model = get_model("mockllm/model", custom_outputs=reply)
    if harness == "codex_cli":
        task.model = CodexModel(task.model)
    started = time.monotonic()
    from inspect_ai.agent._bridge import anthropic_api_impl, completions, responses_impl
    with ExitStack() as stack:
        for module, name in [(anthropic_api_impl, "generate_config_from_anthropic"),
                             (completions, "generate_config_from_openai_completions"),
                             (responses_impl, "generate_config_from_openai_responses")]:
            stack.enter_context(patch.object(module, name, capture(getattr(module, name))))
        eval(task, model_roles={"grader": get_model("mockllm/model", custom_outputs=grade)},
             log_dir=str(args.output / "logs"), display="plain", retry_on_error=0, fail_on_error=False)
    rows = export_rows(args.output)
    row = rows[0]
    print(json.dumps({"seconds": round(time.monotonic() - started, 2), "bridge_calls": calls, "row": row}), flush=True)
    assert row["status"] == ("passed" if args.answer == "reference" else "failed"), row
    assert search_ok
    if args.exa_canary:
        import zipfile
        for archive in (args.output / "logs").glob("*.eval"):
            with zipfile.ZipFile(archive) as log_archive:
                for name in log_archive.namelist():
                    assert b"inert-offline-exa-canary" not in log_archive.read(name), name
    effort = [(request.get("reasoning") or {}).get("effort") or
              (request.get("output_config") or {}).get("effort") or
              request.get("reasoning_effort") for request in requests]
    print(json.dumps({"cli_effort": effort, "cli_models": [request["model"] for request in requests]}), flush=True)
    assert effort and all(value == "high" for value in effort), effort
    assert any("web_search_exa" in name for name in tool_names), tool_names
    assert not tool_names.intersection({"WebSearch", "websearch", "web_search", "web_search_preview", "web__run"}), tool_names
    if evaluation.declaration.type == "build":
        assert len([name for name in row["checks"] if name.startswith("forge:")]) == 8, row
        assert set(name for name in row["checks"] if name.startswith("rubric:")) == {
            "rubric:uses_openzeppelin", "rubric:protects_holders",
        }, row
        assert all(check["passed"] == (args.answer == "reference" or name == "forge:compile")
                   for name, check in row["checks"].items()), row


if __name__ == "__main__":
    main()
