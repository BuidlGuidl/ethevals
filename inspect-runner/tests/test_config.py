from pathlib import Path
import json

from ethevals.config import load_config
from ethevals.loader import load_eval
import pytest

from support import build_task, fixture_config


ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "evals/building/erc20-points-token"


@pytest.mark.parametrize("harness,provider,accepted", [
    ("claude_code", "anthropic", True), ("codex_cli", "openai", True),
    ("claude_code", "openai", False), ("opencode", "openrouter", False),
])
def test_native_search_requires_its_provider(tmp_path, harness, provider, accepted):
    data = fixture_config().model_dump()
    data["models"]["opus-5.5"]["model"] = f"{provider}/test"
    data["prices"][f"{provider}/test"] = data["prices"]["mockllm/opus-5.5"]
    data["agents"]["claude-code-opus-5.5"].update(harness=harness, search="native")
    path = tmp_path / "config.json"
    path.write_text(json.dumps(data))
    if accepted:
        config = load_config(path)
        assert (config.agents["claude-code-opus-5.5"].search, config.models["opus-5.5"].model) == ("native", f"{provider}/test")
    else:
        with pytest.raises(ValueError, match="agents.claude-code-opus-5.5.search: native search requires"):
            load_config(path)


def test_task_uses_configured_limits():
    config = fixture_config()
    config.time_limit, config.cost_limit = 37, 1.25
    task = build_task(load_eval(BUILD, config), config, None, "internet", "reference", 1)
    assert (task.time_limit, task.cost_limit, task.working_limit) == (37, 1.25, None)


@pytest.mark.parametrize("keys,value", [
    (["models", "opus-5.5", "effort"], "hihg"),
    (["agents", "claude-code-opus-5.5", "model"], "missing"),
    (["agents", "claude-code-opus-5.5", "harness"], "absent"),
    (["time_limit"], 0), (["prices"], {}), (["search"], "yes"),
])
def test_config_rejects_invalid_settings(tmp_path, keys, value):
    data = fixture_config().model_dump()
    target = data
    for key in keys[:-1]:
        target = target[key]
    target[keys[-1]] = value
    path = tmp_path / "config.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        load_config(path)
