"""Prove skill discovery through a real CLI with a scripted model reply."""
import argparse
import json
import os
import time
from pathlib import Path

from inspect_ai import eval
from inspect_ai.log import read_eval_log
from inspect_ai.model import ModelOutput, get_model

from ethevals.agents import CodexModel
from ethevals.loader import load_eval
from ethevals.preparation import build_images, prepare_compose
from ethevals.rows import export_rows
from ethevals.skills import skill_index
from support import build_task, fixture_config


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent", choices=["opus", "codex", "kimi"], required=True)
    parser.add_argument("--mode", choices=["skills", "internet"], default="skills")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    assert not any(os.environ.get(name) for name in (
        "OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "OPENAI_API_KEY", "EXA_API_KEY"))
    config = fixture_config()
    config.agents[args.agent].model = "mockllm/model"
    config.grader.model = "mockllm/model"
    config.prices["mockllm/model"] = config.prices["mockllm/model"].model_copy(
        update=dict(input=0, output=0, input_cache_read=0, input_cache_write=0))
    evaluation = load_eval(Path("evals/concepts/agent-registries"), config)
    build_images()
    compose = prepare_compose(evaluation, args.output)
    task = build_task(evaluation, config, args.agent, args.mode, None, 1, compose)
    task.metadata.update(cost_source="mock", grader_cost_source="mock")
    task.model = get_model("mockllm/model", custom_outputs=[ModelOutput.from_content("mockllm/model", "8004")] * 5)
    if config.agents[args.agent].harness == "codex_cli":
        task.model = CodexModel(task.model)
    started = time.monotonic()
    logs = eval(task, model_roles={"grader": get_model("mockllm/model")},
                log_dir=str(args.output / "logs"), display="plain", retry_on_error=0, fail_on_error=False)
    rows = export_rows(args.output)
    elapsed = round(time.monotonic() - started, 2)
    print(json.dumps({"seconds": elapsed, "row": rows[0]}), flush=True)
    assert (rows[0]["mode"], rows[0]["status"]) == (args.mode, "passed"), rows
    log = read_eval_log(logs[0].location, resolve_attachments=True)
    request = next(event for event in log.samples[0].events if event.event == "model")
    (args.output / "first-request.json").write_text(request.model_dump_json(indent=2))
    messages = "\n".join(message.text for message in request.input)
    tools = json.dumps([tool.model_dump(mode="json") for tool in request.tools])
    index = skill_index(evaluation.skills)
    if args.mode == "skills":
        assert index.strip() in messages, "The first request lacks the common index."
        # The native skill declaration appears separately from our common index.
        native = messages.replace(index.strip(), "") + tools
        assert "standards" in native and "Ethereum token and protocol standards" in native, "The first request lacks the native skill declaration."
    else:
        assert "# Ethereum skills" not in messages
        assert "standards/SKILL.md" not in messages + tools
        assert "Ethereum token and protocol standards" not in messages + tools
    print(json.dumps({"mode": args.mode, "index_visible": index.strip() in messages,
                      "first_request": str(args.output / "first-request.json")}), flush=True)


if __name__ == "__main__":
    main()
