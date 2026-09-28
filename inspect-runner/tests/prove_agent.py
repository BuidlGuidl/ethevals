"""Run the real Claude Code binary against scripted, key-free model replies."""
import argparse
import base64
import json
import os
import time
from pathlib import Path

from inspect_ai import eval
from inspect_ai.model import ModelOutput, get_model

from ethevals.config import load_config
from ethevals.loader import load_eval
from ethevals.rows import export_rows
from support import build_task
from ethevals.preparation import prepare_eval, prepare_compose


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("answer", choices=["reference", "empty"])
    parser.add_argument("--eval", default="evals/building/erc20-points-token")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    assert not any(os.environ.get(name) for name in ("OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_AUTH_TOKEN")), "Strip provider credentials before this proof."
    config = load_config()
    config.models["opus"].model = "mockllm/model"
    config.grader.model = "mockllm/model"
    evaluation = load_eval(Path(args.eval), config)
    compose = prepare_compose(evaluation, args.output)
    evaluation = prepare_eval(evaluation, args.output, compose)
    task = build_task(evaluation, config, "opus", "internet", None, 1, compose)
    task.metadata.update(answer_kind=f"scripted_{args.answer}", cost_source="mock", grader_cost_source="mock")
    calls = 0

    def reply(messages, tools, tool_choice, config):
        nonlocal calls
        calls += 1
        if evaluation.declaration.type == "quiz":
            return ModelOutput.from_content("mockllm/model", "ANSWER: C" if evaluation.declaration.choices else "8004")
        if calls == 1 and args.answer == "reference":
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
                f"printf '%s' '{encoded}' | base64 -d > /workspace/src/BuilderPoints.sol"
            )
            return ModelOutput.for_tool_call("mockllm/model", "Bash", {"command": command, "description": "Write the requested token"})
        return ModelOutput.from_content("mockllm/model", "Done.")

    def grade(messages, tools, tool_choice, config):
        request = next(json.loads(message.text) for message in messages if message.text.startswith('{"files"'))
        assert "lib/openzeppelin-contracts/contracts/token/ERC20/ERC20.sol" not in request["files"]
        passed = args.answer == "reference"
        return ModelOutput.from_content("mockllm/model", json.dumps({
            "passed": passed,
            "reason": "The submitted token uses OpenZeppelin without holder controls." if passed else "The workspace contains an empty contract.",
        }))

    task.model = get_model("mockllm/model", custom_outputs=reply)
    started = time.monotonic()
    eval(task, model_roles={"grader": get_model("mockllm/model", custom_outputs=grade)},
         log_dir=str(args.output / "logs"), display="plain", retry_on_error=0, fail_on_error=False)
    rows = export_rows(args.output)
    row = rows[0]
    print(json.dumps({"seconds": round(time.monotonic() - started, 2), "bridge_calls": calls, "row": row}), flush=True)
    assert row["status"] == ("passed" if args.answer == "reference" else "failed"), row
    if evaluation.declaration.type == "build":
        assert len([name for name in row["checks"] if name.startswith("forge:")]) == 8, row
        assert set(name for name in row["checks"] if name.startswith("rubric:")) == {
            "rubric:uses_openzeppelin", "rubric:protects_holders",
        }, row
        assert row["grader_tokens"] > 0, row


if __name__ == "__main__":
    main()
