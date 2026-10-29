import json
from pathlib import Path
import re
import shutil
import tarfile

import pytest

from support import cli, recorded_trial
from test_jobs import job_config, task_folder


ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(("plan_attempt", "matrix_attempt", "expected_name"), [
    (1, 1, "trial-plan-40826749924-1"),
    (1, 2, "trial-plan-40826749924-1"),
    (3, 3, "trial-plan-40826749924-3"),
    (3, 4, "trial-plan-40826749924-3"),
])
def test_matrix_downloads_its_plan_artifact(plan_attempt, matrix_attempt, expected_name):
    import yaml

    jobs = yaml.safe_load((ROOT / ".github/workflows/results.yml").read_text())["jobs"]
    upload = next(step for step in jobs["plan"]["steps"]
                  if step.get("uses", "").startswith("actions/upload-artifact@"))
    download = next(step for step in jobs["matrix"]["steps"]
                    if step.get("uses", "").startswith("actions/download-artifact@"))

    # Resolve only dotted context references in artifact names and job outputs.
    def expand(value, context):
        return re.sub(r"\$\{\{\s*([\w.]+)\s*\}\}", lambda match: context[match[1]], value)

    plan_context = {
        "github.run_id": "40826749924", "github.run_attempt": str(plan_attempt),
        "steps.plan.outputs.matrix": '{"include":[]}',
        "steps.plan.outputs.scheduled_trials": "1", "steps.plan.outputs.sha": "a" * 40,
    }
    uploaded_name = expand(upload["with"]["name"], plan_context)
    matrix_context = {"github.run_id": "40826749924", "github.run_attempt": str(matrix_attempt)}
    matrix_context.update({f"needs.plan.outputs.{key}": expand(value, plan_context)
                           for key, value in jobs["plan"]["outputs"].items()})
    downloaded_name = expand(download["with"]["name"], matrix_context)
    assert uploaded_name == expected_name
    assert downloaded_name == uploaded_name


def test_paid_workflow_limits_secrets_to_the_steps_that_use_them():
    import yaml

    source = (ROOT / ".github/workflows/results.yml").read_text()
    workflow = yaml.safe_load(source)
    exposed = {}
    for job_name, job in workflow["jobs"].items():
        for step in job["steps"]:
            environment = {**workflow.get("env", {}), **job.get("env", {}), **step.get("env", {})}
            secrets = {key: value for key, value in environment.items() if "secrets." in value}
            if secrets:
                exposed[job_name, step.get("name", step.get("uses", step.get("run")))] = secrets
    rpc_names = ["MAINNET_RPC_URL", "BASE_RPC_URL"]
    trial_names = ["CLAUDE_CODE_OAUTH_TOKEN", "CODEX_AUTH_JSON", "OPENROUTER_API_KEY",
                   "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "EXA_API_KEY", *rpc_names]
    assert exposed == {
        ("plan", "Check the budget and emit the matrix"): {name: "${{ secrets." + name + " }}" for name in rpc_names},
        ("matrix", "Run one planned trial"): {name: "${{ secrets." + name + " }}" for name in trial_names},
        ("matrix", "Upload checked trials to Harbor Hub"): {"HARBOR_API_KEY": "${{ secrets.HARBOR_API_KEY }}"},
    }
    for name in [*trial_names, "HARBOR_API_KEY"]:
        assert source.count("${{ secrets." + name + " }}") == 1


def test_ci_plan_holds_judge_errors_without_scheduling_agent_work(tmp_path):
    from ethevals.job_config import load_job
    from ethevals.jobs import plan
    from ethevals.publish import publish_logs
    from ethevals.trial_rows import recover_rows, write_rows

    config_path, task = job_config(tmp_path, "free"), task_folder(tmp_path)
    from test_task_judges import add_judge
    add_judge(task)
    config = load_job(config_path)
    config.agents["local"].name = "oracle"
    config.judge.model, config.judge.paid_by = "openai/gpt-5", "free"
    config_path.write_text(config.model_dump_json())
    item = plan([task], config, [], n_attempts=1)["missing"][0]
    folder = tmp_path / "old/jobs/saved/trial"
    recorded_trial(folder, task)
    private = tmp_path / "host-only.txt"
    private.write_text("OFFLINE-HOST-ONLY")
    (folder / "verifier/planted").symlink_to(private)
    (folder.parent / "board.json").write_text(json.dumps(item))
    previous = tmp_path / "previous.jsonl"
    rows = recover_rows(tmp_path / "old")
    write_rows(previous, rows)
    with pytest.raises(ValueError, match="publication check"):
        publish_logs(tmp_path / "release", "owner/repo", "17", "a" * 40, rows=rows)
    saved = tmp_path / "plan"
    result = cli(ROOT / "scripts/ci.py", "plan-trials", "--config", config_path, "--tasks", task,
                 "--budget", 1, "--n-attempts", 2, "--rows", previous, "--output", saved)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads((saved / "plan.json").read_text())
    assert [row["trial"] for row in report["exhausted_errors"]] == [1]
    admitted = json.loads((saved / "trials.json").read_text())
    assert [[row["trial"] for row in entry["missing"]] for entry in admitted] == [[2]]
    assert sorted(path.name for path in saved.iterdir()) == [
        "config.json", "plan.json", "rows.jsonl", "trials.json"]


def test_run_trial_executes_the_saved_retry_instead_of_planning_again(tmp_path, monkeypatch):
    import argparse
    from harbor.job import Job
    from ethevals.job_config import load_job
    from ethevals.jobs import plan
    from ethevals.trial_rows import write_rows
    from test_ci import ci

    config_path, task = job_config(tmp_path, "free"), task_folder(tmp_path)
    data = json.loads(config_path.read_text())
    data["agents"]["local"]["name"] = "oracle"
    config_path.write_text(json.dumps(data))
    item = plan([task], load_job(config_path), [], n_attempts=1)["missing"][0]
    rows = tmp_path / "previous.jsonl"
    write_rows(rows, [{**item, "schema_version": 8, "retry": 0, "status": "error"}])
    saved = tmp_path / "plan"
    result = cli(ROOT / "scripts/ci.py", "plan-trials", "--config", config_path,
                 "--tasks", task, "--budget", 1, "--n-attempts", 1,
                 "--rows", rows, "--output", saved)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads((saved / "trials.json").read_text())[0]["missing"][0]["retry"] == 1
    calls = []

    async def saved_result(job):
        calls.append(job.config.tasks[0].path)
        recorded_trial(job.job_dir / "trial", task)

    monkeypatch.setattr(Job, "run", saved_result)
    output = tmp_path / "out"
    assert ci.run_trial(argparse.Namespace(plan=saved, index=0, output=output)) == 0
    row = json.loads((output / "rows.jsonl").read_text())
    assert (row["trial"], row["retry"], row["status"]) == (1, 1, "passed")
    assert calls == [task.resolve()]


def test_ci_plan_defers_tasks_with_missing_compose_host_variable(tmp_path, monkeypatch):
    monkeypatch.delenv("ARCHIVE_RPC_URL", raising=False)
    config, task = job_config(tmp_path, "api_key"), task_folder(tmp_path)
    (task / "environment/docker-compose.yaml").write_text(
        "services:\n  browser:\n    environment:\n      URL: ${ARCHIVE_RPC_URL:?Set ARCHIVE_RPC_URL}\n")
    output, github_output = tmp_path / "plan", tmp_path / "github-output"
    result = cli(ROOT / "scripts/ci.py", "plan-trials", "--config", config,
                 "--tasks", task, "--budget", 1, "--rows", tmp_path / "none",
                 "--output", output, "--github-output", github_output)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads((output / "plan.json").read_text())
    assert (report["missing_trials"], report["worst_case_usd"], report["within_budget"]) == (0, 0, True)
    assert [(row["task_id"], row["trial"], row["missing_env"]) for row in report["deferred"]] == [
        ("concepts/question", 1, ["ARCHIVE_RPC_URL"]), ("concepts/question", 2, ["ARCHIVE_RPC_URL"])]
    assert "deferred trials because ARCHIVE_RPC_URL is unset" in result.stderr
    emitted = dict(line.split("=", 1) for line in github_output.read_text().splitlines())
    assert emitted == {"matrix": '{"include":[]}', "scheduled_trials": "0"}
    assert json.loads((output / "trials.json").read_text()) == []
    # The same task becomes eligible as soon as its declared input exists.
    monkeypatch.setenv("ARCHIVE_RPC_URL", "https://archive.example/offline")
    result = cli(ROOT / "scripts/ci.py", "plan-trials", "--config", config,
                 "--tasks", task, "--budget", 12, "--rows", tmp_path / "none",
                 "--output", tmp_path / "available")
    assert result.returncode == 0, result.stdout + result.stderr
    available = json.loads((tmp_path / "available/plan.json").read_text())
    assert (available["missing_trials"], available["deferred"]) == (2, [])


def test_local_run_defers_unavailable_task_and_succeeds_without_harbor(tmp_path, monkeypatch):
    monkeypatch.delenv("ARCHIVE_RPC_URL", raising=False)
    task = task_folder(tmp_path)
    (task / "environment/docker-compose.yaml").write_text(
        "services:\n  browser:\n    environment:\n      URL: ${ARCHIVE_RPC_URL:?Set ARCHIVE_RPC_URL}\n")
    result = cli("-m", "ethevals.cli", "run", "--config", job_config(tmp_path),
                 "--tasks", task, "--budget", 0, "--rows", tmp_path / "none",
                 "--output", tmp_path / "out")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "deferred trials because ARCHIVE_RPC_URL is unset" in result.stderr
    assert not (tmp_path / "out/jobs").exists()


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
    assert [(row["agent_key"], row["trial"], row["plan_group"], row["lane"]) for row in matrix] == [
        ("local", 1, "nop", "plan-nop-0"), ("local", 2, "nop", "plan-nop-1"),
        ("other-model", 1, "nop", "plan-nop-2"), ("other-model", 2, "nop", "plan-nop-3"),
        ("key", 1, "", "key-0"), ("key", 2, "", "key-1")]
    assert emitted["scheduled_trials"] == "6"
    assert all(not Path(row["task_path"]).is_absolute()
               for report in json.loads((output / "trials.json").read_text()) for row in report["missing"])


def test_ci_plan_runs_each_models_vanilla_trials_in_one_job(tmp_path):
    config = job_config(tmp_path, "api_key")
    data = json.loads(config.read_text())
    data["modes"] = ["internet", "vanilla"]
    data["agents"]["bare"] = {"name": "ethevals.vanilla:VanillaAgent", "version": "0.1.0", "model": "local",
                              "modes": ["vanilla"], "paid_by": "api_key", "cost_limit_usd": 2}
    config.write_text(json.dumps(data))
    task = task_folder(tmp_path)
    toml = task / "task.toml"
    toml.write_text(toml.read_text().replace('modes = ["internet"]', 'modes = ["vanilla", "internet"]'))
    output, github_output = tmp_path / "plan", tmp_path / "github-output"
    result = cli(ROOT / "scripts/ci.py", "plan-trials", "--config", config, "--tasks", task,
                 "--modes", "internet", "vanilla", "--budget", 100, "--rows", tmp_path / "none",
                 "--output", output, "--github-output", github_output)
    assert result.returncode == 0, result.stdout + result.stderr
    emitted = dict(line.split("=", 1) for line in github_output.read_text().splitlines())
    matrix = json.loads(emitted["matrix"])["include"]
    assert [(row["agent_key"], row["mode"], row["trial"]) for row in matrix] == [
        ("local", "internet", 1), ("local", "internet", 2), ("bare", "vanilla", "all")]
    trials = json.loads((output / "trials.json").read_text())
    assert [(row["agent_key"], row["trial"]) for row in trials[2]["missing"]] == [("bare", 1), ("bare", 2)]
    assert (trials[2]["missing_trials"], len(trials[2]["selected"])) == (2, 2)
    assert "Deferred" not in result.stderr


def test_ci_defers_plan_trials_beyond_github_queue_capacity(tmp_path):
    output, github_output = tmp_path / "plan", tmp_path / "github-output"
    result = cli(ROOT / "scripts/ci.py", "plan-trials", "--config", job_config(tmp_path),
                 "--tasks", task_folder(tmp_path), "--budget", 1, "--n-attempts", 105,
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
@pytest.mark.parametrize("retry", [False, True])
def test_ci_oracle_trial_survives_artifact_download_and_publishes_locally(tmp_path, monkeypatch, retry):
    private = tmp_path / "private"
    private.mkdir()
    monkeypatch.setenv("TMPDIR", str(private))
    monkeypatch.setenv("CODEX_AUTH_JSON", '{"auth_mode":"chatgpt","tokens":{"access_token":"offline-private-plan-token"}}')
    config = job_config(tmp_path, "free")
    data = json.loads(config.read_text())
    data["agents"]["local"]["name"] = "oracle"
    config.write_text(json.dumps(data))
    plan = tmp_path / "plan"
    previous = tmp_path / "previous.jsonl"
    if retry:
        from ethevals.job_config import load_job
        from ethevals.jobs import plan as plan_job
        from ethevals.trial_rows import write_rows
        item = plan_job([ROOT / "runner/tests/fixtures/harbor/concepts/question"], load_job(config), [], n_attempts=1)["missing"][0]
        write_rows(previous, [{**item, "schema_version": 8, "retry": 0, "status": "error"}])
    result = cli(ROOT / "scripts/ci.py", "plan-trials", "--config", config,
                 "--tasks", ROOT / "runner/tests/fixtures/harbor/concepts/question",
                 "--budget", 1, "--n-attempts", 1, "--rows", previous, "--output", plan)
    assert result.returncode == 0, result.stdout + result.stderr
    output = tmp_path / "original"
    ran = cli(ROOT / "scripts/ci.py", "run-trial", "--plan", plan, "--index", 0, "--output", output)
    assert ran.returncode == 0, ran.stdout + ran.stderr
    row = json.loads((output / "rows.jsonl").read_text())
    assert (row["trial"], row["retry"], row["status"], row["paid_by"]) == (1, 1 if retry else 0, "passed", "free")
    assert list(private.glob("ethevals-auth-*")) == []
    assert all(b"offline-private-plan-token" not in file.read_bytes()
               for file in output.rglob("*") if file.is_file())
    artifact = tmp_path / "download/trial-run-12-1-0"
    shutil.copytree(output / "public", artifact)
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
        assert json.load(archive.extractfile("reward.json")) == row["rewards"]
        assert "reward-details.json" in archive.getnames()
    assert not (combined / "published").exists()
