import json
from pathlib import Path
import shutil
import tarfile

import pytest

from support import cli
from test_jobs import job_config, task_folder


ROOT = Path(__file__).resolve().parents[2]


def test_zero_ci_budget_saves_plan_and_emits_no_jobs_even_for_a_plan(tmp_path):
    output, github_output = tmp_path / "plan", tmp_path / "github-output"
    result = cli(ROOT / "scripts/ci.py", "plan-trials", "--config", job_config(tmp_path),
                 "--tasks", task_folder(tmp_path), "--budget", 0, "--rows", tmp_path / "none",
                 "--output", output, "--github-output", github_output)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads((output / "plan.json").read_text())
    assert (report["missing_trials"], report["worst_case_usd"]) == (2, 0)
    emitted = dict(line.split("=", 1) for line in github_output.read_text().splitlines())
    assert emitted == {"matrix": '{"include":[]}', "scheduled_trials": "0"}
    assert not (output / "jobs").exists()


def test_ci_plan_groups_plan_trials_and_keeps_key_trials_independent(tmp_path):
    config = job_config(tmp_path)
    data = json.loads(config.read_text())
    data["agents"]["other-model"] = {**data["agents"]["local"], "model": "other"}
    data["models"]["other"] = {"name": "local/other"}
    data["agents"]["key"] = {**data["agents"]["local"], "name": "key-agent", "paid_by": "api_key"}
    config.write_text(json.dumps(data))
    output, github_output = tmp_path / "plan", tmp_path / "github-output"
    result = cli(ROOT / "scripts/ci.py", "plan-trials", "--config", config,
                 "--tasks", task_folder(tmp_path), "--budget", 12, "--rows", tmp_path / "none",
                 "--output", output, "--github-output", github_output)
    assert result.returncode == 0, result.stdout + result.stderr
    emitted = dict(line.split("=", 1) for line in github_output.read_text().splitlines())
    matrix = json.loads(emitted["matrix"])["include"]
    assert [(row["agent_key"], row["trial"], row["plan_group"]) for row in matrix] == [
        ("local", 1, "nop"), ("local", 2, "nop"),
        ("other-model", 1, "nop"), ("other-model", 2, "nop"),
        ("key", 1, ""), ("key", 2, "")]
    assert emitted["scheduled_trials"] == "6"
    assert all(not Path(row["task_path"]).is_absolute() for row in json.loads((output / "trials.json").read_text()))


def test_ci_defers_plan_trials_beyond_github_queue_capacity(tmp_path):
    output, github_output = tmp_path / "plan", tmp_path / "github-output"
    result = cli(ROOT / "scripts/ci.py", "plan-trials", "--config", job_config(tmp_path),
                 "--tasks", task_folder(tmp_path), "--budget", 1, "--trials", 105,
                 "--rows", tmp_path / "none", "--output", output, "--github-output", github_output)
    assert result.returncode == 0, result.stdout + result.stderr
    emitted = dict(line.split("=", 1) for line in github_output.read_text().splitlines())
    assert emitted["scheduled_trials"] == "100"
    assert len(json.loads(emitted["matrix"])["include"]) == 100
    assert "Deferred 5 trials" in result.stderr


def test_ci_refuses_an_insufficient_positive_budget(tmp_path):
    output, github_output = tmp_path / "plan", tmp_path / "github-output"
    result = cli(ROOT / "scripts/ci.py", "plan-trials", "--config", job_config(tmp_path, "api_key"),
                 "--tasks", task_folder(tmp_path), "--budget", 1, "--rows", tmp_path / "none",
                 "--output", output, "--github-output", github_output)
    assert result.returncode == 1
    report = json.loads((output / "plan.json").read_text())
    assert (report["worst_case_usd"], report["within_budget"]) == (12, False)
    assert json.loads((output / "trials.json").read_text()) == []


@pytest.mark.docker
def test_ci_oracle_trial_survives_artifact_download_and_publishes_locally(tmp_path, monkeypatch):
    private = tmp_path / "private"
    private.mkdir()
    monkeypatch.setenv("TMPDIR", str(private))
    monkeypatch.setenv("CODEX_AUTH_JSON", '{"tokens":{"access_token":"offline-private-plan-token"}}')
    config = job_config(tmp_path, "free")
    data = json.loads(config.read_text())
    data["agents"]["local"]["name"] = "oracle"
    config.write_text(json.dumps(data))
    plan = tmp_path / "plan"
    result = cli(ROOT / "scripts/ci.py", "plan-trials", "--config", config,
                 "--tasks", ROOT / "runner/tests/fixtures/harbor/question",
                 "--budget", 1, "--trials", 1, "--rows", tmp_path / "none", "--output", plan)
    assert result.returncode == 0, result.stdout + result.stderr
    output = tmp_path / "original"
    ran = cli(ROOT / "scripts/ci.py", "run-trial", "--plan", plan, "--index", 0, "--output", output)
    assert ran.returncode == 0, ran.stdout + ran.stderr
    row = json.loads((output / "rows.jsonl").read_text())
    assert (row["trial"], row["attempt"], row["status"], row["paid_by"]) == (1, 1, "passed", "free")
    assert list(private.glob("ethevals-auth-*")) == []
    assert all(b"offline-private-plan-token" not in file.read_bytes()
               for file in output.rglob("*") if file.is_file())
    artifact = tmp_path / "download/trial-run-12-1-0"
    shutil.copytree(output, artifact)
    shutil.rmtree(output)
    # Recovery must read the downloaded files, not stale paths or aggregate rows.
    (artifact / "rows.jsonl").unlink()
    published = cli(ROOT / "scripts/ci.py", "publish-results", "--output", artifact.parent,
                    "--repo", "owner/repo", "--run-id", "12", "--commit", "b" * 40)
    assert published.returncode == 0, published.stdout + published.stderr
    combined = artifact.parent / "combined"
    report = json.loads((combined / "release.json").read_text())
    row = json.loads((combined / "rows.jsonl").read_text())
    assert row["status"] == "passed"
    assert row["checks"] == {"unit": {"passed": True, "reason": "The final reply matches."}}
    assert row["trajectory_url"].startswith("https://github.com/owner/repo/releases/download/results-12/trajectory-")
    trajectory = next(asset for asset in report["assets"] if asset["name"].endswith(".json"))
    assert json.loads(Path(trajectory["source"]).read_text())["steps"][-1]["message"] == "metre"
    verifier = next(asset for asset in report["assets"] if asset["name"].endswith(".tar.gz"))
    with tarfile.open(verifier["source"]) as archive:
        assert json.load(archive.extractfile("checks.json")) == row["checks"]
        assert archive.extractfile("reward.txt").read().strip() == b"1"
    assert not (combined / "published").exists()
