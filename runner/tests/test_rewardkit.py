import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from ethevals.trial_rows import results_row
from ethevals.checks import read_reward
from ethevals.images.tag import image_tag


IMAGES = Path(__file__).resolve().parents[1] / "ethevals/images"


@pytest.mark.parametrize("passed,expected", [(True, 1.0), (False, 0.0)])
def test_check_records_become_named_rewardkit_criteria_and_board_checks(tmp_path, passed, expected):
    tests = tmp_path / "tests"
    tests.mkdir()
    shutil.copy(IMAGES / "check_records.py", tests)
    (tests / "reward.toml").write_text(
        '[scoring.check_records]\naggregation = "all-pass"\n'
        '[[reward]]\nname = "reward"\naggregation = "all-pass"\n')
    (tests / "structure").mkdir()
    (tests / "structure/check.py").write_text(
        'from rewardkit import criterion\n'
        '@criterion\ndef manifest_exists(workspace):\n'
        '    return {"score": True, "reasoning": "Manifest exists."}\n')
    folder = tmp_path / "trial"
    shutil.copytree(Path(__file__).parent / "fixtures/harbor/recorded-trial", folder)
    records = folder / "verifier/checks.json"
    records.write_text(json.dumps({
        "compile": {"passed": True, "reason": "Compilation passed."},
        "test_result": {"passed": passed, "reason": "Expected value."},
    }))
    result = subprocess.run([
        "rewardkit", str(tests), "--workspace", str(tmp_path),
        "--output", str(folder / "verifier/reward.json"),
    ], env={**os.environ, "CHECKS_FILE": str(records)}, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    rewards = json.loads((folder / "verifier/reward.json").read_text())
    assert rewards == {"check_records": expected, "structure": 1.0, "reward": expected}
    saved = json.loads((folder / "result.json").read_text())
    saved["verifier_result"]["rewards"] = rewards
    (folder / "result.json").write_text(json.dumps(saved))
    records.unlink()
    metadata = json.loads((folder / "board.json").read_text())
    row = results_row(folder, metadata)
    assert (row["status"], row["rewards"], row["checks"]) == (
        "passed" if passed else "failed", rewards, {
            "compile": {"passed": True, "reason": "Compilation passed."},
            "test_result": {"passed": passed, "reason": "Expected value."},
            "manifest_exists": {"passed": True, "reason": "Manifest exists."},
        })


@pytest.mark.docker
def test_quiz_rewardkit_verifier_needs_no_network(tmp_path):
    tests, logs = tmp_path / "tests", tmp_path / "logs"
    tests.mkdir()
    (logs / "agent").mkdir(parents=True)
    (logs / "agent/trajectory.json").write_text(json.dumps({"steps": [
        {"source": "agent", "message": "metre"}]}))
    (tests / "answer.py").write_text(
        'import sys\nsys.path.insert(0, "/opt")\n'
        'import target_checks\nimport rewardkit as rk\n'
        'rk.final_answer(lambda reply: reply == "metre", name="unit")\n')
    image = "ghcr.io/buidlguidl/" + image_tag(image="quiz")
    subprocess.run(["docker", "build", "-f", str(IMAGES / "Quiz.Dockerfile"),
                    "-t", image, str(IMAGES)], check=True, capture_output=True)
    result = subprocess.run([
        "docker", "run", "--rm", "--network", "none", "--entrypoint", "sh",
        "-v", f"{tests}:/tests:ro", "-v", f"{logs}:/logs", image, "-c",
        'python3 -c \'from importlib.metadata import version; assert version("harbor-rewardkit") == "0.2.3"\' && rewardkit /tests',
    ], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert read_reward(logs / "verifier") == (
        {"reward": 1.0}, {"unit": {"passed": True, "reason": "Answer matches the target."}})
