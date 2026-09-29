from pathlib import Path
import json
import shutil

from ethevals.config import load_config
from ethevals.loader import load_eval
import pytest
import yaml

from conftest import fixture_config
from support import build_task, eval_cli


ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "evals/building/erc20-points-token"


def test_validate_rejects_effort_typo(folder, tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(fixture_config().model_dump()).replace("effort: high", "effort: hihg"))
    result = eval_cli("validate", "--evals", folder, "--config", path)
    assert result.returncode == 2
    assert "agents.opus.effort" in result.stderr


def test_type_time_limit_reaches_task(tmp_path):
    folder = tmp_path / "concepts/quiz"
    shutil.copytree(ROOT / "evals/concepts/agent-registries", folder)
    path = folder / "eval.yaml"
    config = fixture_config()
    config.time_limits["quiz"] = 123
    config.cost_limit = 0.25
    task = build_task(load_eval(folder, config), config, None, "vanilla", "reference", 1)
    assert (task.working_limit, task.time_limit, task.cost_limit) == (123, 369, 0.25)


def test_unknown_harness_fails_at_config_load(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(fixture_config().model_dump()).replace("harness: claude_code", "harness: absent"))
    with pytest.raises(ValueError, match="unknown harness 'absent'"):
        fixture_config(path)


def test_build_rejects_scoring_window_that_cannot_fit():
    config = fixture_config()
    evaluation = load_eval(BUILD, config)
    config.time_limits["build"] = 300
    with pytest.raises(ValueError, match="Scoring needs 540 seconds, but Inspect allows 450"):
        build_task(evaluation, config, None, "internet", "reference", 1)


@pytest.mark.parametrize("key,value,diagnostic", [
    ("time_limits", {"quiz": 0, "build": 1200, "act": 1200}, "time_limits.quiz"),
    ("prices", {}, "prices.mockllm/grader"),
    ("search", "yes", "search"),
])
def test_config_errors_name_file_and_key(tmp_path, key, value, diagnostic):
    path = tmp_path / "config.yaml"
    data = fixture_config().model_dump()
    data[key] = value
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError) as error:
        load_config(path)
    assert str(path) in str(error.value)
    assert diagnostic in str(error.value)
