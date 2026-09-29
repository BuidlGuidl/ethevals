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
from inspect_ai.log import read_eval_log
from inspect_ai.model import ContentText, ContentToolUse, ModelOutput, get_model

from support import build_task, fixture_config, valid_search_result
from ethevals.loader import load_eval
from ethevals.rows import export_rows
from ethevals.preparation import build_images, prepare_compose
from ethevals.skills import skill_index


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("answer", choices=["reference", "empty"])
    parser.add_argument("--agent", choices=list(fixture_config().agents), required=True)
    parser.add_argument("--eval", default="inspect-runner/tests/fixtures/building/erc20-points-token")
    parser.add_argument("--mode", choices=["internet", "skills"], default="internet")
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
    settings = config.agents[args.agent]
    native_search = settings.harness in {"claude_code", "codex_cli"} and not args.exa_canary
    settings.search = "native" if native_search else "exa"
    model = config.models[settings.model]
    model.model = "mockllm/model"
    config.grader.model = "mockllm/model"
    evaluation = load_eval(Path(args.eval), config)
    build_images()
    compose = prepare_compose(evaluation, args.output)
    task = build_task(evaluation, config, args.agent, args.mode, None, 1, compose)
    task.metadata.update(free_check=True, cost_source="mock", grader_cost_source="mock")
    calls = 0
    tool_names = set()
    harness = settings.harness
    cli_identity = settings.cli_model
    requests = []
    efforts = []
    search_ok = False
    search_call = 2 if harness == "codex_cli" and not native_search else 1
    work_call = search_call + 1 + (native_search and harness == "claude_code")
    search_marker = "native-search-proof-8004"

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
        efforts.append(config.reasoning_effort)
        assert config.reasoning_effort == model.effort, config.reasoning_effort
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
        if harness == "codex_cli" and not native_search and calls == 1:
            return ModelOutput.for_tool_call("mockllm/model", "tool_search", {
                "query": "exa web_search_exa", "limit": 1,
            })
        if native_search and calls < work_call:
            if harness == "claude_code" and calls == 1:
                assert "WebSearch" in tool_names, tool_names
                return ModelOutput.for_tool_call("mockllm/model", "WebSearch", {"query": "Ethereum ERC-8004"})
            search_tool = next((tool for tool in tools if tool.name == "web_search"), None)
            assert search_tool is not None, f"{harness} offered no native web_search tool: {sorted(tool_names)}"
            if harness == "claude_code":
                assert search_tool.options["anthropic"]["max_uses"] == 8, search_tool
            else:
                assert "openai" in search_tool.options, search_tool
            print(json.dumps({"native_search_tool": search_tool.model_dump(mode="json")}), flush=True)
            result = json.dumps([{"type": "web_search_result", "url": "https://eips.ethereum.org/EIPS/eip-8004",
                                  "title": search_marker, "encrypted_content": "cHJvb2Y="}])
            block = ContentToolUse(tool_type="web_search", id="srvtoolu_native_proof", name="web_search" if harness == "claude_code" else "search",
                                   arguments=json.dumps({"type": "search", "query": search_marker}), result=result)
            output = ModelOutput.from_content("mockllm/model", search_marker) if harness == "claude_code" else ModelOutput.for_tool_call(
                "mockllm/model", "exec_command", {"cmd": "true"})
            output.message.content = [block, ContentText(text=search_marker)]
            return output
        if native_search and calls == work_call:
            assert search_marker in json.dumps(requests[-1]), "The CLI did not return the native search result."
            if harness == "codex_cli":
                search = next(item for item in requests[-1]["input"] if item.get("type") == "web_search_call")
                assert (search["id"], search["action"]["query"]) == ("srvtoolu_native_proof", search_marker), search
            search_ok = True
            print(json.dumps({"native_search_received_by_cli": harness, "marker": search_marker}), flush=True)
        if not native_search and calls == search_call:
            arguments = {"query": "site:ethereum.org ERC-20 token standard", "numResults": 1,
                         "objective": "Find the official ERC-20 token standard and its methods."}
            name = next(name for name in tool_names if "web_search_exa" in name)
            return ModelOutput.for_tool_call("mockllm/model", name, arguments)
        if not native_search and calls == work_call:
            result = next(message for message in reversed(messages) if message.role == "tool")
            assert not result.error, result
            assert valid_search_result(result.text), result.text
            assert "ERC" in result.text or "token" in result.text.lower(), result.text
            search_ok = True
            print(json.dumps({"exa_search": "passed", "result": result.text}), flush=True)
        if evaluation.declaration.type == "quiz":
            if args.answer == "empty":
                return ModelOutput.from_content("mockllm/model", "No answer.")
            return ModelOutput.from_content("mockllm/model", "ANSWER: C" if evaluation.declaration.choices else "8004")
        if calls == work_call and args.answer == "reference":
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
                name, arguments = "exec_command", {"cmd": command}
            else:
                name = "Bash" if harness == "claude_code" else "bash"
                arguments = {"command": command, "description": "Write the requested token"}
            return ModelOutput.for_tool_call("mockllm/model", name, arguments)
        if evaluation.declaration.type == "act" and args.answer == "reference" and calls == work_call + 1:
            command = r'''read_value() { sed -n 's/.*"'"$1"'": "\([^"]*\)".*/\1/p' chain.json; }; cast call "$(read_value token)" "balanceOf(address)(uint256)" "$(read_value recipient)" --rpc-url "$(read_value rpc_url)"'''
            return ModelOutput.for_tool_call("mockllm/model", "Bash", {
                "command": command, "description": "Confirm the recipient balance before reporting success"})
        return ModelOutput.from_content("mockllm/model", "Done.")

    def grade(messages, tools, tool_choice, config):
        evidence = json.loads(messages[1].text)
        if evaluation.declaration.type == "act" and args.answer == "reference":
            call = next(call for message in evidence for call in message.get("tool_calls", [])
                        if "balanceOf(address)(uint256)" in call["arguments"].get("command", ""))
            result = next(message for message in evidence if message.get("tool_call_id") == call["id"])
            assert set(call) == {"id", "function", "arguments"}, call
            assert set(result) == {"role", "tool_call_id", "function", "content"}, result
            assert result["role"] == "tool" and result["function"] == "Bash", result
            assert "12500000" in result["content"], result
            print(json.dumps({"grader_balance_check": call, "grader_balance_result": result}), flush=True)
        elif evaluation.declaration.type == "build":
            assert "src/BuilderPoints.sol" in evidence
            assert "lib/openzeppelin-contracts/contracts/token/ERC20/ERC20.sol" not in evidence
        passed = args.answer == "reference"
        return ModelOutput.from_content("mockllm/model", json.dumps({
            "passed": passed,
            "reason": ("The agent checked the recipient balance before reporting success." if evaluation.declaration.type == "act"
                       else "The submitted token uses OpenZeppelin without holder controls.") if passed else "No completed work.",
        }))

    provider = task.model.source if harness == "codex_cli" else task.model
    started = time.monotonic()
    from inspect_ai.agent._bridge import anthropic_api_impl, completions, responses_impl
    with ExitStack() as stack:
        stack.enter_context(patch.object(provider.api, "outputs", reply))
        for module, name in [(anthropic_api_impl, "generate_config_from_anthropic"),
                             (completions, "generate_config_from_openai_completions"),
                             (responses_impl, "generate_config_from_openai_responses")]:
            stack.enter_context(patch.object(module, name, capture(getattr(module, name))))
        logs = eval(task, model_roles={"grader": get_model("mockllm/model", custom_outputs=grade)},
             log_dir=str(args.output / "logs"), display="plain", retry_on_error=0, fail_on_error=False)
    rows = export_rows(args.output)
    row = rows[0]
    print(json.dumps({"seconds": round(time.monotonic() - started, 2), "bridge_calls": calls, "row": row}), flush=True)
    assert row["status"] == ("passed" if args.answer == "reference" else "failed"), row
    assert search_ok
    assert row["mode"] == args.mode, row
    log = read_eval_log(logs[0].location, resolve_attachments=True)
    usage = sum(item.total_cost for item in log.samples[0].model_usage.values())
    assert abs(row["model_cost_usd"] - (usage - row["grader_cost_usd"])) < 1e-9
    request = next(event for event in log.samples[0].events if event.event == "model")
    (args.output / "first-request.json").write_text(request.model_dump_json(indent=2))
    messages = "\n".join(message.text for message in request.input)
    tools = json.dumps([tool.model_dump(mode="json") for tool in request.tools])
    if args.mode == "skills":
        index = skill_index(evaluation.skills).strip()
        assert index in messages, "The first request lacks the common index."
        native = messages.replace(index, "") + tools
        assert "standards" in native and "Ethereum token and protocol standards" in native, "The first request lacks the native skill entry."
    else:
        assert "# Ethereum skills" not in messages, "The internet request contains the skills index."
        assert "Ethereum token and protocol standards" not in messages + tools, "The internet request contains the native skill entry."
        print(json.dumps({"internet_skills_absent": True}), flush=True)
    if args.exa_canary:
        import zipfile
        for archive in (args.output / "logs").glob("*.eval"):
            with zipfile.ZipFile(archive) as log_archive:
                for name in log_archive.namelist():
                    assert b"inert-offline-exa-canary" not in log_archive.read(name), name
    print(json.dumps({"bridge_effort": efforts, "cli_models": [request["model"] for request in requests]}), flush=True)
    assert efforts and all(value == model.effort for value in efforts), efforts
    if native_search:
        assert not any("exa" in name for name in tool_names), tool_names
    else:
        assert any("web_search_exa" in name for name in tool_names), tool_names
        assert not tool_names.intersection({"WebSearch", "websearch", "web_search", "web_search_preview", "web__run"}), tool_names
    if evaluation.declaration.type == "act":
        assert row["checks"]["rubric:verified_transfer"]["passed"] == (args.answer == "reference"), row
    if evaluation.declaration.type == "build":
        assert len([name for name in row["checks"] if name.startswith("forge:")]) == 8, row
        assert set(name for name in row["checks"] if name.startswith("rubric:")) == {
            "rubric:uses_openzeppelin", "rubric:protects_holders",
        }, row
        assert all(check["passed"] == (args.answer == "reference" or name == "forge:compile")
                   for name, check in row["checks"].items()), row


if __name__ == "__main__":
    main()
