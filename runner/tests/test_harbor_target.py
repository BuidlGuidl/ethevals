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


@pytest.mark.parametrize("task_name,check,message,expected", [
    ("permit2-zero-expiration", "zero_expiration", message, expected)
    for message, expected in [
        ("**No.** In Permit2, an expiration of 0 is stored as the current `block.timestamp`, ...", True),
        ("No. Permit2 converts expiration `0` to the approval block's timestamp, ...", True),
        ("No — Permit2's `transferFrom` reverts `AllowanceExpired` unless ...", True),
        ("Yes. In Permit2, `expiration == 0` is treated as non-expiring, ...", False),
        ('Yes — Permit2 treats an `expiration` of `0` in `approve` as "no expiration" ...', False),
        ("Not sure; it depends.", False),
        ("Nothing expires.", False),
        (" \n***nO!*** The approval expired.", True),
        ("", False),
    ]
] + [
    ("permit2-7702-signature", "signature_check", message, expected)
    for message, expected in [
        ("**ERC-1271**  Permit2's `SignatureVerification` uses ecrecover only when ...", True),
        ("ERC-1271 — Permit2 checks `owner.code.length`, ...", True),
        ("**ERC-1271.**  Because after EIP-7702 delegation ...", True),
        ("**ecrecover**  Permit2's SignatureVerification library validates all signatures via ECDSA recovery ...", False),
        ("ecrecover — the EOA's key signed it.", False),
        (" \n***erc1271.*** The account has code.", True),
        ("(eip-1271). The account has code.", True),
        ("ERC-12710", False),
        ("", False),
    ]
])
def test_permit2_targets_grade_final_replies(tmp_path, task_name, check, message, expected):
    import shutil

    task = Path(__file__).resolve().parents[2] / "tasks/concepts" / task_name
    tests, output = tmp_path / "tests", tmp_path / "verifier"
    trajectory = tmp_path / "trajectory.json"
    tests.mkdir()
    trajectory.write_text(json.dumps({"steps": [{"source": "agent", "message": message}]}))
    (tests / "answer.py").write_text((task / "tests/answer.py").read_text().replace(
        "    name=", f"    trajectory={str(trajectory)!r},\n    name="))
    shutil.copyfile(task / "tests/reward.toml", tests / "reward.toml")
    result = subprocess.run(["rewardkit", str(tests), "--output", str(output / "reward.json")],
        env={**os.environ, "PYTHONPATH": str(HELPER.parent)}, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    reason = "Answer matches the target." if expected else "Answer does not match the target."
    if not message.strip():
        reason = "The answer is empty."
    assert read_reward(output) == ({"reward": float(expected)}, {check: {"passed": expected, "reason": reason}})
