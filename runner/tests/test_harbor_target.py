import json
from pathlib import Path

import pytest

from support import cli


HELPER = Path(__file__).resolve().parents[1] / "ethevals/images/target_checks.py"


@pytest.mark.parametrize("message,tool_calls,target,expected,reason", [
    ("The unit is metre.", None, {"target": "metre", "location": "end"}, True, "Answer matches the target."),
    ([{"type": "text", "text": "METRE"}], None, {"target": ["metre", "meter"]}, True, "Answer matches the target."),
    ("kilometre", None, {"target": "metre"}, False, "Answer does not match the target."),
    ("metre", [{"tool_call_id": "call-1"}], {"target": "metre"}, False, "The answer is empty."),
    ("", None, {"target": "metre"}, False, "The answer is empty."),
])
def test_shared_target_verifier_reads_the_final_reply(tmp_path, message, tool_calls, target, expected, reason):
    trajectory, settings, output = tmp_path / "trajectory.json", tmp_path / "target.json", tmp_path / "verifier"
    trajectory.write_text(json.dumps({"steps": [
        {"source": "user", "message": "metre"},
        {"source": "agent", "message": message, "tool_calls": tool_calls}]}))
    settings.write_text(json.dumps({"name": "unit", **target}))
    result = cli(HELPER, settings, "--trajectory", trajectory, "--output", output)
    assert result.returncode == 0, result.stderr
    assert json.loads((output / "checks.json").read_text()) == {"unit": {"passed": expected, "reason": reason}}
    assert (output / "reward.txt").read_text() == f"{int(expected)}\n"
