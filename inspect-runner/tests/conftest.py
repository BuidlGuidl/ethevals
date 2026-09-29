from pathlib import Path
import shutil

from ethevals.config import Config, load_config as read_config
from ethevals.loader import load_eval
from ethevals.preparation import prepare_compose
from ethevals.rows import results_rows
from inspect_ai import eval
from inspect_ai.model import GenerateConfig, ModelOutput, ModelUsage, get_model
import pytest
import yaml

from support import build_task


ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "evals/building/erc20-points-token"


def pytest_addoption(parser):
    parser.addoption("--run-docker", action="store_true", help="Run the real Docker and Forge proofs.")
    parser.addoption("--run-live-exa", action="store_true", help="Check the keyless hosted Exa tool snapshot.")


def pytest_configure(config):
    config.addinivalue_line("markers", "docker: requires the local runner image and Docker")
    config.addinivalue_line("markers", "live_exa: calls the keyless hosted Exa service")


def pytest_collection_modifyitems(config, items):
    for item in items:
        if "live_exa" in item.keywords and not config.getoption("--run-live-exa"):
            item.add_marker(pytest.mark.skip(reason="Use --run-live-exa for hosted parity."))
    if not config.getoption("--run-docker"):
        for item in items:
            if "docker" in item.keywords:
                item.add_marker(pytest.mark.skip(reason="Use --run-docker to run Docker proofs."))


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
                                                    "mockllm/grader", "mockllm/model", "mockllm/agent",
                                                    "mockllm/shared"]})


def small_config():
    prices = dict(input=1, output=1, input_cache_read=1, input_cache_write=1)
    model = dict(model="mockllm/test", effort="high")
    return Config(epochs=3, time_limits={"quiz": 10, "build": 1200, "act": 1200}, cost_limit=2, max_attempts=2,
                  concurrency=1, search=False, search_limit=20, search_price_usd=0.05, prices={"mockllm/test": prices},
                  grader={**model, "max_tokens": 10},
                  agents={"test": {**model, "harness": None}})


@pytest.fixture
def folder(tmp_path):
    target = tmp_path / "concepts" / "quiz"
    shutil.copytree(ROOT / "evals/concepts/agent-registries", target)
    return target


@pytest.fixture
def scoring_case(tmp_path):
    config = fixture_config()
    config.agents["opus"].model = "mockllm/agent"
    config.grader.model = "mockllm/grader"
    folder = tmp_path / "building/token"
    shutil.copytree(BUILD, folder)
    (folder / "scorer/solution/src/BuilderPoints.sol").write_text("pragma solidity ^0.8.30; contract Token {}")
    (folder / "scorer/tests/BuilderPoints.t.sol").unlink()
    (folder / "scorer/tests/Token.t.sol").write_text(
        'pragma solidity ^0.8.30; import "../src/BuilderPoints.sol"; '
        'contract TokenTest { function testSupply() public { new Token(); } }')
    evaluation = load_eval(folder, config)
    task = build_task(evaluation, config, "opus", "internet", None, 1, prepare_compose(evaluation, tmp_path))
    from ethevals.checks import solution
    task.solver = solution(evaluation, "reference")
    case = {"task": task, "requests": [], "configs": []}

    def execute(replies, budget=None):
        if budget is not None:
            task.dataset[0].metadata["grader_cost_limit_usd"] = budget
        pending = iter(replies)

        async def grade(messages, tools, tool_choice, config):
            import anyio
            case["requests"].append(messages)
            case["configs"].append(config)
            reply = next(pending)
            if isinstance(reply, tuple):
                delay, reply = reply
                await anyio.sleep(delay)
            if isinstance(reply, Exception):
                raise reply
            output = ModelOutput.from_content("mockllm/grader", reply)
            output.usage = ModelUsage(input_tokens=100, output_tokens=100, total_tokens=200)
            return output

        log = eval(task, model_roles={"grader": get_model("mockllm/grader", custom_outputs=grade,
                   config=GenerateConfig(max_tokens=config.grader.max_tokens, reasoning_effort=config.grader.effort))},
                   log_dir=str(tmp_path / "logs"), display="none")[0]
        case["log"] = log
        return results_rows(log)[0]

    case["run"] = execute
    return case


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


@pytest.fixture
def config_path(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(fixture_config().model_dump_json())
    return path
