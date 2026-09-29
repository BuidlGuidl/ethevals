from pathlib import Path
from tempfile import TemporaryDirectory
import json
import os
import re
import subprocess
import sys

from ethevals.actors import select_actors
from ethevals.config import Config, load_config as read_config
from ethevals.loader import load_eval
from ethevals.preparation import prepare_compose
from ethevals.runner import build_task as actor_task, run
from inspect_ai.solver import solver
import anyio
import yaml


ROOT = Path(__file__).resolve().parents[2]
INPUTS = TemporaryDirectory()


def fixture_config(path=None):
    if path is not None:
        return read_config(path)
    models = {key: {"model": f"mockllm/{key}", "effort": "low"}
              for key in ("opus-5.5", "gpt-6-sol", "kimi-k3", "glm-5.3")}
    prices = dict(input=5.0, output=25.0, input_cache_read=0.5, input_cache_write=6.25)
    return Config(epochs=3, time_limits={"quiz": 300, "build": 1200, "act": 1200}, cost_limit=5,
                  max_attempts=2, concurrency=1, search=True, search_limit=20, search_price_usd=0.05,
                  grader={"model": "mockllm/grader", "effort": "low", "max_tokens": 4096}, models=models,
                  agents={
                      "claude-code-opus-5.5": dict(harness="claude_code", model="opus-5.5", cli_model="claude-opus-5-5"),
                      "codex-cli-gpt-6-sol": dict(harness="codex_cli", model="gpt-6-sol", cli_model="gpt-6-sol"),
                      "opencode-kimi-k3": dict(harness="opencode", model="kimi-k3", cli_model="openrouter/moonshotai/kimi-k3"),
                      "opencode-glm-5.3": dict(harness="opencode", model="glm-5.3", cli_model="openrouter/z-ai/glm-5.3"),
                  }, prices={name: prices for name in [*(item["model"] for item in models.values()),
                             "mockllm/grader", "mockllm/model", "mockllm/agent", "mockllm/shared"]})


def small_config():
    prices = dict(input=1, output=1, input_cache_read=1, input_cache_write=1)
    model = dict(model="mockllm/test", effort="high")
    return Config(epochs=3, time_limits={"quiz": 10, "build": 1200, "act": 1200}, cost_limit=2, max_attempts=2,
                  concurrency=1, search=False, search_limit=20, search_price_usd=0.05, prices={"mockllm/test": prices},
                  grader={**model, "max_tokens": 10},
                  models={"test": model},
                  agents={"test-agent": {"model": "test", "harness": "claude_code", "cli_model": "test"}})


def fixture_quiz(tmp_path, name="units", *, modes=None, choices=None, **scorer):
    folder = tmp_path / "concepts" / name
    (folder / "workspace").mkdir(parents=True)
    (folder / "scorer").mkdir()
    (folder / "eval.yaml").write_text(yaml.safe_dump({"type": "quiz", "motivation": "Check units.",
        "prompt": "Give the unit.", "modes": modes or ["vanilla"], "choices": choices}))
    (folder / "scorer/target.yaml").write_text(yaml.safe_dump({"target": "wei", **scorer}))
    return load_eval(folder, fixture_config())


def catalog_quiz():
    config = fixture_config()
    return config, load_eval(ROOT / "evals/concepts/agent-registries", config)


def build_task(evaluation, config, key, mode, answer, epochs, compose=None):
    selection = {"models" if mode == "vanilla" else "agents": [key]} if not answer else {}
    actors_for, grade = select_actors(config, modes=[mode], answer=answer, **selection)
    actor = actors_for(evaluation)[0][1]
    if compose is None and actor.sandbox_for(evaluation):
        compose = prepare_compose(evaluation, Path(INPUTS.name))
    return actor_task(evaluation, config, actor, grade, mode, epochs, compose)


@solver
def mock_delay(seconds):
    async def solve(state, generate):
        await anyio.sleep(seconds)
        return state
    return solve


def search_text(result):
    if isinstance(result, str):
        # Codex wraps an MCP object with its script timing and output lines.
        start = result.find('{"content"')
        if start >= 0:
            try:
                result = json.JSONDecoder().raw_decode(result[start:])[0]
            except ValueError:
                pass
        else:
            try:
                result = json.loads(result)
            except ValueError:
                return result, False
    if isinstance(result, dict):
        text, error = search_text(result.get("content", ""))
        return text, error or bool(result.get("isError"))
    if isinstance(result, list):
        return "\n".join(item.get("text", "") if isinstance(item, dict) else getattr(item, "text", "")
                         for item in result), False
    return str(result), False


def search_result_status(result):
    text, error = search_text(result)
    prefix = text[:300].lower()
    limited = any(marker in prefix for marker in ("exa's free mcp rate limit", "rate limit exceeded",
                                                   "rate_limit", "too many requests"))
    failed = error or limited or prefix.startswith(("error", "search failed"))
    return limited, failed


def valid_search_result(result):
    text, error = search_text(result)
    return not error and not search_result_status(result)[1] and all(
        re.search(pattern, text, re.MULTILINE) for pattern in
        (r"^Title: .+", r"^URL: https?://\S+", r"^(?:Highlights|Content|Text):"))


def cli(*args):
    environment = {key: value for key, value in os.environ.items() if key not in {
        "OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_AUTH_TOKEN", "EXA_API_KEY", "GH_TOKEN", "HF_TOKEN",
        "PYTEST_CURRENT_TEST"}}
    return subprocess.run([sys.executable, *map(str, args)], cwd=Path(__file__).resolve().parents[2], env=environment,
                          capture_output=True, text=True, timeout=60)


def eval_cli(*args):
    with TemporaryDirectory() as directory:
        config = Path(directory) / "config.json"
        config.write_text(fixture_config().model_dump_json())
        flags = [] if "--config" in args else ["--config", config]
        return cli("-m", "ethevals.cli", *args, *flags)
