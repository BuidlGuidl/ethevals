from pathlib import Path
from tempfile import TemporaryDirectory
import json
import os
import re
import subprocess
import sys

from ethevals.actors import agent, grader
from ethevals.checks import check_agent, check_grader
from ethevals.preparation import prepare_compose
from ethevals.runner import build_task as actor_task, run
from inspect_ai.solver import solver
import anyio


INPUTS = TemporaryDirectory()


def build_task(evaluation, config, key, mode, answer, epochs, compose=None):
    actor = check_agent(evaluation, answer, mode=mode) if answer else agent(config, key, mode)
    grade = check_grader() if answer else grader(config)
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
    from conftest import fixture_config
    with TemporaryDirectory() as directory:
        config = Path(directory) / "config.json"
        config.write_text(fixture_config().model_dump_json())
        flags = [] if "--config" in args else ["--config", config]
        return cli("-m", "ethevals.cli", *args, *flags)
