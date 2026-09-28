"""Run a real agent binary against scripted, key-free model replies."""
import argparse
import base64
import json
import os
import re
import time
from pathlib import Path

from inspect_ai import eval
from inspect_ai.model import GenerateConfig, ModelOutput, get_model

from ethevals.config import load_config
from ethevals.loader import load_eval
from ethevals.rows import export_rows
from support import build_task
from ethevals.preparation import prepare_eval


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("answer", choices=["reference", "empty"])
    parser.add_argument("--model", choices=["opus", "codex", "kimi", "glm"], default="opus")
    parser.add_argument("--eval", default="evals/building/erc20-points-token")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    assert not any(os.environ.get(name) for name in ("OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_AUTH_TOKEN")), "Strip provider credentials before this proof."
    config = load_config()
    config.models[args.model].model = "mockllm/model"
    config.grader.model = "mockllm/model"
    evaluation = load_eval(Path(args.eval), config)
    evaluation = prepare_eval(evaluation, args.output)
    task = build_task(evaluation, config, args.model, "internet", None, 1)
    task.metadata.update(answer_kind=f"scripted_{args.answer}", cost_source="mock", grader_cost_source="mock")
    calls = 0
    tool_names = set()

    def reply(messages, tools, tool_choice, config):
        nonlocal calls
        calls += 1
        tool_names.update(tool.name for tool in tools)
        if args.model == "codex":
            for message in messages:
                if message.role == "tool":
                    tool_names.update(re.findall(r'"([A-Za-z_]+)"', message.text))
        print(json.dumps({"bridge_call": calls, "tools": sorted(tool_names), "effort": config.reasoning_effort}), flush=True)
        assert config.reasoning_effort == "high", config
        if args.model == "codex" and calls == 1:
            return ModelOutput.for_tool_call("mockllm/model", "exec", {
                "input": "text(ALL_TOOLS.map(tool => tool.name));",
            })
        if evaluation.declaration.type == "quiz":
            return ModelOutput.from_content("mockllm/model", "ANSWER: C" if evaluation.declaration.choices else "8004")
        if calls == (2 if args.model == "codex" else 1) and args.answer == "reference":
            solution = (evaluation.folder / "scorer/solution/src/BuilderPoints.sol").read_bytes()
            encoded = base64.b64encode(solution).decode()
            command = (
                "test ! -e /workspace/scorer && test ! -e /workspace/test/BuilderPoints.t.sol && "
                "test ! -e /workspace/rubric.md && "
                f"printf '%s' '{encoded}' | base64 -d > /workspace/src/BuilderPoints.sol"
            )
            if args.model == "codex":
                name, arguments = "exec", {"input": "text(await tools.exec_command(" + json.dumps({"cmd": command}) + "));"}
            else:
                name = "Bash" if args.model == "opus" else "bash"
                arguments = {"command": command, "description": "Write the requested token"}
            return ModelOutput.for_tool_call("mockllm/model", name, arguments)
        return ModelOutput.from_content("mockllm/model", "Done.")

    def grade(messages, tools, tool_choice, config):
        request = next(json.loads(message.text) for message in messages if message.text.startswith('{"files"'))
        assert "lib/openzeppelin-contracts/contracts/token/ERC20/ERC20.sol" not in request["files"]
        passed = args.answer == "reference"
        return ModelOutput.from_content("mockllm/model", json.dumps({
            "passed": passed,
            "reason": "The submitted token uses OpenZeppelin without holder controls." if passed else "The workspace contains an empty contract.",
        }))

    task.model = get_model("mockllm/model", config=GenerateConfig(reasoning_effort=config.models[args.model].effort), custom_outputs=reply)
    started = time.monotonic()
    eval(task, model_roles={"grader": get_model("mockllm/model", custom_outputs=grade)},
         log_dir=str(args.output / "logs"), display="plain", retry_on_error=0, fail_on_error=False)
    rows = export_rows(args.output)
    row = rows[0]
    print(json.dumps({"seconds": round(time.monotonic() - started, 2), "bridge_calls": calls, "row": row}), flush=True)
    assert row["status"] == ("passed" if args.answer == "reference" else "failed"), row
    assert any("web_search_exa" in name for name in tool_names), tool_names
    assert not tool_names.intersection({"WebSearch", "websearch", "web_search", "web_search_preview", "web__run"}), tool_names
    if evaluation.declaration.type == "build":
        assert len([name for name in row["checks"] if name.startswith("forge:")]) == 8, row
        assert set(name for name in row["checks"] if name.startswith("rubric:")) == {
            "rubric:uses_openzeppelin", "rubric:protects_holders",
        }, row
        assert row["grader_tokens"] > 0, row
        assert all(check["passed"] == (args.answer == "reference" or name == "forge:compile")
                   for name, check in row["checks"].items()), row


if __name__ == "__main__":
    main()
