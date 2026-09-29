import json

import pytest

from ethevals.config import load_config
from ethevals.loader import load_eval
from support import fixture_config


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


def test_scenario_is_parked(tmp_path):
    folder = tmp_path / "concepts/review"
    (folder / "workspace").mkdir(parents=True)
    (folder / "scorer").mkdir()
    (folder / "scorer/scorer.yaml").write_text("scorers: []\n")
    path = folder / "eval.yaml"
    path.write_text("type: scenario\nprompt: Review this.\nmotivation: Check review.\nmodes: [internet]\n")
    with pytest.raises(ValueError) as error:
        load_eval(folder, fixture_config())
    assert str(error.value) == f"{path.resolve()}: type: scenario is not supported yet"
