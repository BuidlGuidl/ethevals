import json
import os
from pathlib import Path
import subprocess

import pytest

from ethevals.checks import read_reward


HELPER = Path(__file__).resolve().parents[1] / "ethevals/images/target_checks.py"


@pytest.mark.parametrize("message,tool_calls,expected,reason", [
    ("metre.", None, True, "Answer matches the target."),
    ([{"type": "text", "text": "METER"}], None, True, "Answer matches the target."),
    ("kilometre", None, False, "Answer does not match the target."),
    ("metre", [{"tool_call_id": "call-1"}], False, "The answer is empty."),
    ("", None, False, "The answer is empty."),
])
def test_shared_target_verifier_reads_the_final_reply(tmp_path, message, tool_calls, expected, reason):
    trajectory, tests, output = tmp_path / "trajectory.json", tmp_path / "tests", tmp_path / "verifier"
    tests.mkdir()
    trajectory.write_text(json.dumps({"steps": [
        {"source": "user", "message": "metre"},
        {"source": "agent", "message": message, "tool_calls": tool_calls}]}))
    (tests / "answer.py").write_text(
        'import target_checks\nimport rewardkit as rk\n'
        f'rk.final_answer(lambda reply: reply.strip(" .").casefold() in ["metre", "meter"], '
        f'trajectory={str(trajectory)!r}, name="unit")\n')
    result = subprocess.run(["rewardkit", str(tests), "--output", str(output / "reward.json")],
        env={**os.environ, "PYTHONPATH": str(HELPER.parent)}, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert read_reward(output) == ({"reward": float(expected)}, {"unit": {"passed": expected, "reason": reason}})
