import json
import re

import anyio
from inspect_ai.solver import solver

from ethevals.actors import player, grader
from ethevals.checks import check_player, check_grader
from ethevals.config import Config, load_config as read_config
from ethevals.runner import build_task as actor_task
from ethevals.runner import run
from pathlib import Path
from tempfile import TemporaryDirectory
from ethevals.preparation import prepare_compose

INPUTS = TemporaryDirectory()


def build_task(evaluation, config, key, mode, answer, epochs, compose=None):
    actor = check_player(evaluation, answer, mode=mode) if answer else player(config, key, mode)
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


def fixture_config(path=None):
    if path is not None:
        return read_config(path)
    prices = dict(input=5.0, output=25.0, input_cache_read=0.5, input_cache_write=6.25)
    agents = {key: dict(model=f"mockllm/{key}", effort="high", harness=harness,
                       agent_model_config=cli_model)
              for key, harness, cli_model in [("opus", "claude_code", "claude-opus-5-5"),
                  ("codex", "codex_cli", "gpt-6-sol"), ("kimi", "opencode", "openrouter/moonshotai/kimi-k3"),
                  ("glm", "opencode", "openrouter/z-ai/glm-5.3")]}
    return Config(epochs=3, time_limits={"quiz": 300, "build": 1200, "act": 1200},
                  cost_limit=5.0, max_attempts=2, concurrency=1, search=True, search_limit=20, search_price_usd=0.05,
                  grader=dict(model="mockllm/grader", effort="none", max_tokens=4096),
                  agents=agents,
                  prices={name: prices for name in [*(item["model"] for item in agents.values()),
                                                    "mockllm/grader", "mockllm/model", "mockllm/player",
                                                    "mockllm/shared"]})


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
