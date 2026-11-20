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


def test_weighted_mean_ignores_zero_weight_and_keeps_fractional_reward_in_row(tmp_path):
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "findings.py").write_text(
        'import rewardkit as rk\n'
        'rk.file_exists("first.txt", name="first")\n'
        'rk.file_exists("second.txt", name="second")\n')
    (tests / "report.py").write_text('import rewardkit as rk\nrk.file_exists("report.txt", name="report")\n')
    (tests / "reward.toml").write_text(
        '[scoring.findings]\naggregation = "weighted-mean"\n'
        '[scoring.report]\naggregation = "all-pass"\n'
        '[[reward]]\nname = "reward"\naggregation = "weighted-mean"\nweights = { findings = 1, report = 0 }\n')
    (tmp_path / "first.txt").touch()
    (tmp_path / "report.txt").touch()
    folder = tmp_path / "trial"
    shutil.copytree(Path(__file__).parent / "fixtures/harbor/recorded-trial", folder)
    reward_path = folder / "verifier/reward.json"
    result = subprocess.run([
        "rewardkit", str(tests), "--workspace", str(tmp_path), "--output", str(reward_path),
    ], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    rewards = json.loads(reward_path.read_text())
    assert rewards == {"reward": 0.5}
    saved = json.loads((folder / "result.json").read_text())
    saved["verifier_result"]["rewards"] = rewards
    (folder / "result.json").write_text(json.dumps(saved))
    row = results_row(folder, json.loads((folder / "board.json").read_text()))
    assert (row["schema_version"], row["status"], row["rewards"]) == (8, "failed", {"reward": 0.5})
    assert {name: check["passed"] for name, check in row["checks"].items()} == {
        "first": True, "second": False, "report": True,
    }


@pytest.mark.parametrize("found,report,reward,status", [
    (6, True, 1.0, "passed"),
    (3, True, 0.5, "failed"),
    (2, True, 0.3333, "failed"),
    (0, True, 0.0, "failed"),
    (0, False, 0.0, "failed"),
], ids=["finds-all-six", "finds-three", "finds-two", "nothing-matches", "no-report"])
def test_partial_credit_scenarios_for_six_findings(tmp_path, found, report, reward, status):
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "findings.py").write_text("import rewardkit as rk\n" + "".join(
        f'rk.file_exists("finding-{number}.txt", name="finding_{number}")\n' for number in range(6)))
    (tests / "report.py").write_text('import rewardkit as rk\nrk.file_exists("report.txt", name="report_written")\n')
    (tests / "reward.toml").write_text(
        '[scoring.findings]\naggregation = "weighted-mean"\n'
        '[scoring.report]\naggregation = "all-pass"\n'
        '[[reward]]\nname = "reward"\naggregation = "weighted-mean"\nweights = { findings = 1, report = 0 }\n')
    for number in range(found):
        (tmp_path / f"finding-{number}.txt").touch()
    if report:
        (tmp_path / "report.txt").touch()
    folder = tmp_path / "trial"
    shutil.copytree(Path(__file__).parent / "fixtures/harbor/recorded-trial", folder)
    reward_path = folder / "verifier/reward.json"
    result = subprocess.run([
        "rewardkit", str(tests), "--workspace", str(tmp_path), "--output", str(reward_path),
    ], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    rewards = json.loads(reward_path.read_text())
    assert rewards == {"reward": reward}
    saved = json.loads((folder / "result.json").read_text())
    saved["verifier_result"]["rewards"] = rewards
    (folder / "result.json").write_text(json.dumps(saved))
    row = results_row(folder, json.loads((folder / "board.json").read_text()))
    assert (row["status"], row["rewards"]) == (status, {"reward": reward})
    assert sum(check["passed"] for name, check in row["checks"].items() if name != "report_written") == found


@pytest.mark.parametrize("reward", [-0.01, 1.01])
def test_reward_outside_unit_interval_is_rejected(tmp_path, reward):
    path = tmp_path / "reward.json"
    path.write_text(json.dumps({"reward": reward}))
    with pytest.raises(ValueError, match=r"reward\.json: RewardKit must write reward between 0 and 1"):
        read_reward(tmp_path)


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
