import json
from pathlib import Path

from support import cli
import pytest


def job_config(tmp_path, paid_by="plan"):
    path = tmp_path / "job.json"
    path.write_text(json.dumps({
        "harbor_version": "0.24.0", "time_limit": 60, "trials": 2, "max_attempts": 2,
        "modes": ["internet"],
        "models": {"local": {"name": "local/model", "effort": "high"}},
        "agents": {"local": {"name": "nop", "version": "1.0.0", "model": "local",
                              "paid_by": paid_by, "cost_limit_usd": 3}},
    }))
    return path


def task_folder(tmp_path):
    task = tmp_path / "tasks/concepts/question"
    for name in ["environment", "tests", "solution"]:
        (task / name).mkdir(parents=True)
    (task / "task.toml").write_text(
        'schema_version = "1.3"\n[metadata]\npillar = "concepts"\n'
        'motivation = "Check a reply."\nmodes = ["internet"]\n')
    (task / "instruction.md").write_text("Name a unit.\n")
    (task / "environment/Dockerfile").write_text("FROM debian:bookworm-slim\n")
    (task / "tests/test.sh").write_text("#!/bin/sh\nexit 0\n")
    (task / "solution/solve.sh").write_text("#!/bin/sh\nexit 0\n")
    return task


def test_plan_reserves_no_agent_spend_for_a_plan_but_run_requires_budget(tmp_path):
    config, task = job_config(tmp_path), task_folder(tmp_path)
    args = ["--config", config, "--tasks", task, "--output", tmp_path / "out",
            "--rows", tmp_path / "missing.jsonl"]
    planned = cli("-m", "ethevals.cli", "plan", *args)
    assert planned.returncode == 0, planned.stderr
    report = json.loads(planned.stdout)
    assert [(row["trial"], row["attempt"], row["agent_reserve_usd"]) for row in report["missing"]] == [
        (1, 1, 0), (2, 1, 0)]
    assert report["worst_case_usd"] == 0
    refused = cli("-m", "ethevals.cli", "run", *args)
    assert refused.returncode == 2
    assert "requires --budget" in refused.stderr
    assert not (tmp_path / "out/jobs").exists()


def test_row_builder_reads_a_recorded_real_trial(tmp_path):
    from ethevals.trial_rows import results_row

    folder = Path(__file__).parent / "fixtures/harbor/recorded-trial"
    metadata = json.loads((folder / "board.json").read_text())
    row = results_row(folder, metadata, trajectory_url="https://example.org/trajectory.json")
    assert (row["task_id"], row["status"], row["paid_by"], row["model_cost_usd"], row["total_tokens"]) == (
        "concepts/question", "passed", "free", 0, 0)
    assert row["checks"] == {"unit": {"passed": True, "reason": "The final reply matches."}}
    assert row["trajectory_url"] == "https://example.org/trajectory.json"
    assert row["total_seconds"] > 0


def test_published_trajectory_enriches_the_same_attempt_and_a_later_error_stays_latest():
    from ethevals.trial_rows import fold_rows, results_row

    folder = Path(__file__).parent / "fixtures/harbor/recorded-trial"
    row = results_row(folder, json.loads((folder / "board.json").read_text()))
    published = {**row, "trajectory_url": "https://example.org/trajectory.json"}
    assert fold_rows([row], [published])[0]["trajectory_url"] == "https://example.org/trajectory.json"
    assert fold_rows([published], [row])[0]["trajectory_url"] == "https://example.org/trajectory.json"
    later = {**row, "attempt": 2, "status": "error", "error_kind": "execution", "error_reason": "Agent stopped."}
    assert [(item["attempt"], item["status"]) for item in fold_rows([published], [later])] == [(2, "error")]


def test_planner_recovers_finished_trials_and_repeats_changed_tasks(tmp_path):
    import shutil
    from ethevals.jobs import load_job, plan, task_entry
    from ethevals.trial_rows import previous_rows

    config, task = load_job(job_config(tmp_path, "free")), task_folder(tmp_path)
    config.agents["local"].name = "oracle"
    folder = Path(__file__).parent / "fixtures/harbor/recorded-trial"
    metadata = json.loads((folder / "board.json").read_text())
    metadata["task_hash"] = task_entry(task)["hash"]
    job = tmp_path / "out/jobs/recorded"
    shutil.copytree(folder, job / "trial")
    (job / "board.json").write_text(json.dumps(metadata))
    prior = previous_rows(tmp_path / "out", tmp_path / "none")
    pending = plan([task], config, prior)
    assert [(row["trial"], row["attempt"]) for row in pending["missing"]] == [(2, 1)]
    (task / "instruction.md").write_text("Name a different unit.\n")
    assert [(row["trial"], row["attempt"]) for row in plan([task], config, prior)["missing"]] == [(1, 1), (2, 1)]


def test_api_key_budget_reserves_remaining_attempts_and_retains_exhausted_errors(tmp_path):
    from ethevals.jobs import budget_check, load_job, plan

    config, task = load_job(job_config(tmp_path, "api_key")), task_folder(tmp_path)
    missing = plan([task], config, [])["missing"]
    previous = [{**row, "status": "error", "attempt": index + 1} for index, row in enumerate(missing)]
    report = budget_check(plan([task], config, previous), 2)
    assert [(row["trial"], row["attempt"], row["remaining_attempts"], row["worst_case_usd"])
            for row in report["missing"]] == [(1, 2, 1, 3)]
    assert [(row["trial"], row["attempt"]) for row in report["exhausted_errors"]] == [(2, 2)]
    assert (report["worst_case_usd"], report["within_budget"]) == (3, False)
    retried = plan([task], config, previous, retry_errors=True)
    assert [(row["trial"], row["attempt"]) for row in retried["missing"]] == [(1, 2), (2, 3)]


@pytest.mark.parametrize("budget", ["-1", "nan", "inf"])
def test_cli_rejects_bad_budgets_without_starting_harbor(tmp_path, budget):
    result = cli("-m", "ethevals.cli", "run", "--config", job_config(tmp_path), "--tasks", task_folder(tmp_path),
                 "--budget", budget, "--output", tmp_path / "out", "--rows", tmp_path / "none")
    assert result.returncode == 2
    assert "finite, nonnegative" in result.stderr
    assert not (tmp_path / "out/jobs").exists()


def test_cli_rejects_an_api_key_reserve_above_the_budget(tmp_path):
    output = tmp_path / "out"
    result = cli("-m", "ethevals.cli", "run", "--config", job_config(tmp_path, "api_key"),
                 "--tasks", task_folder(tmp_path), "--budget", 0, "--output", output,
                 "--rows", tmp_path / "none")
    assert result.returncode == 2
    assert "Budget exceeded; no trials started" in result.stderr
    report = json.loads((output / "plan.json").read_text())
    assert (report["missing_trials"], report["worst_case_usd"], report["within_budget"]) == (2, 12, False)
    assert not (output / "jobs").exists()


@pytest.mark.parametrize("selection,message", [
    (["--agents", "absent"], "Unknown agent: absent"),
    (["--models", "absent"], "Unknown model: absent"),
    (["--modes", "skills"], "Selected modes must be listed in the job config"),
    (["--trial", "1"], None),
])
def test_cli_selects_configured_entries(tmp_path, selection, message):
    output = tmp_path / "out"
    result = cli("-m", "ethevals.cli", "plan", "--config", job_config(tmp_path),
                 "--tasks", task_folder(tmp_path), "--output", output, "--rows", tmp_path / "none", *selection)
    if message:
        assert result.returncode == 2
        assert message in result.stderr
    else:
        assert result.returncode == 0, result.stderr
        assert [(row["trial"], row["model"], row["agent"]) for row in json.loads(result.stdout)["missing"]] == [
            (1, "local/model", "nop")]


def test_catalog_contains_only_public_task_fields(tmp_path):
    task = task_folder(tmp_path)
    (task / "tests/private.txt").write_text("Do not publish the verifier in the catalog.")
    output = tmp_path / "catalog"
    result = cli("-m", "ethevals.cli", "catalog", "--tasks", task, "--output", output)
    assert result.returncode == 0, result.stderr
    catalog = json.loads((output / "catalog.json").read_text())
    entry = catalog["tasks"][0]
    assert {key: value for key, value in entry.items() if key != "hash"} == {
        "id": "concepts/question", "pillar": "concepts", "motivation": "Check a reply.",
        "instruction": "Name a unit.\n", "modes": ["internet"]}
    assert len(entry["hash"]) == 64


def test_invalid_check_records_become_retryable_verification_errors(tmp_path):
    import shutil
    from ethevals.trial_rows import results_row

    fixture = Path(__file__).parent / "fixtures/harbor/recorded-trial"
    shutil.copytree(fixture, tmp_path / "trial")
    metadata = json.loads((fixture / "board.json").read_text())
    (tmp_path / "trial/verifier/checks.json").write_text('{"unit":{"passed":"true","reason":"Matches."}}')
    row = results_row(tmp_path / "trial", metadata)
    assert (row["status"], row["error_kind"], row["error_reason"], row["checks"]) == (
        "error", "verification", "Each check needs a name, boolean passed, and one-line reason.", {})


@pytest.mark.docker
@pytest.mark.parametrize("paid_by", ["api_key", "plan"])
def test_any_configured_agent_keeps_api_price_cost_when_a_plan_or_key_pays(tmp_path, monkeypatch, paid_by):
    import os

    config = job_config(tmp_path, paid_by)
    data = json.loads(config.read_text())
    data["agents"]["local"]["name"] = "local_agent:LocalAgent"
    data["agents"]["local"]["kwargs"] = {"delay": 2}
    data["time_limit"] = 1
    config.write_text(json.dumps(data))
    fixture = Path(__file__).parent / "fixtures/harbor"
    monkeypatch.setenv("PYTHONPATH", str(fixture.resolve()) + os.pathsep + os.environ.get("PYTHONPATH", ""))
    result = cli("-m", "ethevals.cli", "run", "--config", config, "--tasks", fixture / "question",
                 "--trial", 2, "--budget", 6 if paid_by == "api_key" else 0,
                 "--output", tmp_path / "out", "--rows", tmp_path / "none")
    assert result.returncode == 0, result.stdout + result.stderr
    row = json.loads((tmp_path / "out/rows.jsonl").read_text())
    assert (row["trial"], row["status"], row["model_cost_usd"], row["total_tokens"], row["paid_by"]) == (
        2, "passed", 0.01234, 110, paid_by)
    assert row["limit"]["type"] == "time"
    assert row["limit"]["limit"] == 1
    trial_config = json.loads(next((tmp_path / "out/jobs").glob("*/*/config.json")).read_text())
    assert trial_config["agent"]["kwargs"] == {"delay": 2, "version": "1.0.0", "reasoning_effort": "high"}


@pytest.mark.docker
def test_killed_job_resumes_without_repeating_its_finished_trial(tmp_path):
    import os
    import signal
    import subprocess
    import sys
    import time

    config = job_config(tmp_path, "free")
    data = json.loads(config.read_text())
    data["agents"]["local"]["name"] = "oracle"
    config.write_text(json.dumps(data))
    task = Path(__file__).parent / "fixtures/harbor/question"
    output = tmp_path / "out"
    args = [sys.executable, "-m", "ethevals.cli", "run", "--config", str(config),
            "--tasks", str(task), "--output", str(output), "--rows", str(tmp_path / "none"), "--budget", "0"]
    with (tmp_path / "killed-stdout.txt").open("w") as stdout:
        process = subprocess.Popen(args, stdout=stdout, stderr=subprocess.STDOUT, start_new_session=True)
        finished = []
        try:
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline and process.poll() is None:
                for path in (output / "jobs").glob("*/*/result.json"):
                    try:
                        result = json.loads(path.read_text())
                    except ValueError:
                        continue
                    if result.get("finished_at") and not result.get("exception_info"):
                        finished.append(path)
                if finished:
                    os.killpg(process.pid, signal.SIGTERM)
                    break
                time.sleep(0.01)
            process.wait(timeout=20)
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
    assert process.returncode == -signal.SIGTERM
    assert len(finished) == 1
    before = finished[0].read_bytes()
    resumed = subprocess.run(args, capture_output=True, text=True, timeout=120)
    assert resumed.returncode == 0, resumed.stdout + resumed.stderr
    assert finished[0].read_bytes() == before
    assert len(list((output / "jobs").glob("*/*/result.json"))) == 2
    rows = [json.loads(line) for line in (output / "rows.jsonl").read_text().splitlines()]
    assert [(row["trial"], row["attempt"], row["status"]) for row in rows] == [(1, 1, "passed"), (2, 1, "passed")]


@pytest.mark.docker
def test_cli_runs_a_real_oracle_and_recovers_rows_without_repeating_finished_trials(tmp_path):
    import shutil

    config = job_config(tmp_path, "free")
    data = json.loads(config.read_text())
    data["agents"]["local"]["name"] = "oracle"
    data["trials"] = 1
    config.write_text(json.dumps(data))
    task = Path(__file__).parent / "fixtures/harbor/question"
    output = tmp_path / "out"
    args = ["--config", config, "--tasks", task, "--output", output, "--rows", tmp_path / "absent.jsonl"]
    ran = cli("-m", "ethevals.cli", "run", *args, "--budget", "0")
    assert ran.returncode == 0, ran.stdout + ran.stderr
    row = json.loads((output / "rows.jsonl").read_text())
    assert (row["status"], row["trial"], row["model_cost_usd"], row["paid_by"], row["judge"]) == (
        "passed", 1, 0, "free", None)
    assert row["checks"] == {"unit": {"passed": True, "reason": "The final reply matches."}}
    assert json.loads(Path(row["trajectory_file"]).read_text())["steps"][-1]["message"] == "metre"
    assert row["trajectory_url"].startswith("/trajectories/")
    results = list((output / "jobs").glob("*/*/result.json"))
    assert len(results) == 1
    before = results[0].read_bytes()
    # A kill can lose the aggregate rows after Harbor saves the finished trial.
    (output / "rows.jsonl").unlink()
    resumed = cli("-m", "ethevals.cli", "run", *args)
    assert resumed.returncode == 0, resumed.stdout + resumed.stderr
    assert list((output / "jobs").glob("*/*/result.json")) == results
    assert results[0].read_bytes() == before
    assert json.loads((output / "rows.jsonl").read_text())["status"] == "passed"
    fixture = tmp_path / "recorded-trial"
    shutil.copytree(results[0].parent, fixture)
