import asyncio
import json
from pathlib import Path
import shlex
import shutil
from types import SimpleNamespace

import pytest

from ethevals.job_config import load_job
from ethevals.jobs import plan, run, budget_check
from ethevals.trial_rows import results_row, write_rows, read_rows
from support import recorded_trial
from test_jobs import job_config, task_folder
from test_task_judges import add_judge


def saved_page(tmp_path):
    original = task_folder(tmp_path)
    task = tmp_path / "tasks/build/question"
    task.parent.mkdir()
    original.rename(task)
    settings = task / "task.toml"
    settings.write_text('artifacts = [{source = "/workspace", exclude = ["node_modules", "dist", ".git", "chain_context.json"]}]\n'
                        + settings.read_text().replace('pillar = "concepts"', 'pillar = "build"'))
    config = load_job(job_config(tmp_path, "free"))
    item, = plan([task], config, [], n_attempts=1)["missing"]
    folder = tmp_path / "saved"
    recorded_trial(folder, task)
    (folder / "artifacts/workspace").mkdir(parents=True)
    (folder / "artifacts/workspace/app.txt").write_text("Saved page.")
    (folder / "artifacts/manifest.json").write_text(json.dumps([{
        "source": "/workspace", "destination": "artifacts/workspace", "status": "ok", "service": None,
        "exclude": ["node_modules", "dist", ".git", "chain_context.json"]}]))
    return task, config, results_row(folder, item)


@pytest.mark.parametrize("changed", ["tests/test.sh", "verifier"])
def test_page_changes_regrade_passes_and_fails_while_missing_work_reruns(tmp_path, changed):
    task, config, row = saved_page(tmp_path)
    if changed == "verifier":
        with (task / "task.toml").open("a") as file:
            file.write("\n[verifier]\ntimeout_sec = 120\n")
    else:
        (task / changed).write_text("Changed checks.\n")
    gone = {**row, "trial": 3, "verifier_files": None, "verifier_url": None}
    report = plan([task], config, [row, {**row, "trial": 2, "status": "failed"}, gone],
                  n_attempts=3, saved_work=tmp_path / "cache")
    assert [(item["trial"], item["kind"], item["checks_generation"]) for item in report["regrades"]] == [
        (1, "workspace", 1), (2, "workspace", 1)]
    assert [(item["trial"], item["rerun_reason"]) for item in report["missing"]] == [
        (3, "Saved work is gone: No saved work is published")]


@pytest.mark.parametrize("task_name", ["build/keeper-deposits", "build/signed-votes", "act/aave-borrow"])
def test_partial_workspaces_and_act_tasks_keep_their_reruns(tmp_path, monkeypatch, task_name):
    from ethevals.harbor_tasks import task_host_variables
    root = Path(__file__).resolve().parents[2]
    source = root / "tasks" / task_name
    if not source.exists():
        source = next((root / "tasks/act").iterdir())
    task = tmp_path / "tasks" / source.parent.name / source.name
    shutil.copytree(source, task)
    for name in task_host_variables(task):
        monkeypatch.setenv(name, "offline-rpc")
    config = load_job(job_config(tmp_path, "free"))
    item, = plan([task], config, [], n_attempts=1)["missing"]
    (task / "tests/test.sh").write_text("Changed checks.\n")
    report = plan([task], config, [{**item, "status": "passed"}], n_attempts=1)
    assert (report["regrade_trials"], report["missing"][0]["rerun_reason"]) == (
        0, "The changed checks need a live browser or chain.")


def test_page_judge_changes_keep_the_judge_only_regrade(tmp_path):
    from ethevals.jobs import task_entry
    from ethevals.regrade import regrade_options
    task, config, row = saved_page(tmp_path)
    add_judge(task)
    old = task_entry(task, config)
    row.update(**{key: old[key] for key in ("checks_hash", "checks_inputs")}, judge={"model": "saved"})
    verifier = Path(row["verifier_files"])
    (verifier / "reward-details.json").write_text(json.dumps({"reward": {"kind": "llm", "criteria": [],
        "judge": {"files": None, "atif_trajectory": "/logs/agent/trajectory.json"}}}))
    judge = task / "tests/judge.toml"
    judge.write_text(judge.read_text().replace("explain the unit?", "explain the unit correctly?"))
    report = plan([task], config, [row], n_attempts=1, saved_work=tmp_path / "cache")
    assert (regrade_options(task)["kind"], report["missing_trials"],
            [(item["kind"], item["judge_required"]) for item in report["regrades"]]) == (
        "workspace", 0, [("judge", True)])


def test_page_work_removed_from_ci_reruns_while_other_rows_regrade(tmp_path, monkeypatch):
    import subprocess
    from ethevals import saved_work
    task, config, row = saved_page(tmp_path)
    (task / "tests/test.sh").write_text("Changed checks.\n")
    missing = {**row, "trial": 2, "verifier_files": None,
               "verifier_url": "https://github.com/owner/repo/releases/download/results-42/verifier-old.tar.gz"}

    def download(command, **kwargs):
        raise subprocess.CalledProcessError(1, command, stderr=b"No artifacts match.")

    monkeypatch.setattr(saved_work.subprocess, "run", download)
    monkeypatch.setattr(saved_work.subprocess, "check_output", lambda *args, **kwargs: "")
    report = plan([task], config, [row, missing], n_attempts=2, saved_work=tmp_path / "cache")
    assert ([(item["trial"], item["kind"]) for item in report["regrades"]],
            [(item["trial"], item["rerun_reason"]) for item in report["missing"]]) == (
        [(1, "workspace")], [(2, "Saved work is gone: No CI artifacts match trial-plan-42-*")])


def test_page_trial_archive_fetch_also_restores_its_separate_verifier_context(tmp_path, monkeypatch):
    import io
    import tarfile
    from ethevals.saved_work import fetch_work
    from ethevals import saved_work
    _, _, row = saved_page(tmp_path)
    source = Path(row["verifier_files"]).parent
    (source / "verifier/fixture.json").write_text('{"treasury":"saved"}')
    payloads = {}
    for name, paths in [("trial", ["artifacts"]), ("verifier", ["verifier/fixture.json"])]:
        data = io.BytesIO()
        with tarfile.open(fileobj=data, mode="w:gz") as archive:
            for path in paths:
                archive.add(source / path, arcname=path if name == "trial" else "fixture.json")
        payloads[f"https://example.org/{name}.tar.gz"] = data.getvalue()
    fetched = []

    def download(url, **kwargs):
        fetched.append(url)
        return io.BytesIO(payloads[url])

    monkeypatch.setattr(saved_work, "urlopen", download)
    row.update(verifier_files=None, artifacts_url="https://example.org/trial.tar.gz", verifier_url="https://example.org/verifier.tar.gz")
    work = fetch_work(row, "workspace", tmp_path / "cache")
    assert (fetched, (Path(work["trial"]) / "artifacts/workspace/app.txt").read_text(),
            json.loads((Path(work["trial"]) / "verifier/fixture.json").read_text())) == (
        ["https://example.org/trial.tar.gz", "https://example.org/verifier.tar.gz"], "Saved page.", {"treasury": "saved"})


@pytest.mark.parametrize("context_file", ["fixture.json", "chain_context.json"])
def test_saved_agent_restores_files_dependencies_and_public_setup_values(tmp_path, monkeypatch, context_file):
    from ethevals.saved_agent import SavedWorkAgent
    import subprocess
    task, config, row = saved_page(tmp_path)
    trial = Path(row["verifier_files"]).parent
    source = trial / "artifacts/workspace"
    (source / "package.json").write_text('{"dependencies":{"added":"1.2.3"}}')
    (source / "pnpm-lock.yaml").write_text("saved-lockfile")
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    (fresh / "starter.txt").write_text("Must disappear.")
    (fresh / "node_modules").mkdir()
    (fresh / "node_modules/old.txt").write_text("Image dependency.")
    context = tmp_path / "chain/chain_context.json"
    context.parent.mkdir()
    context.write_text(json.dumps({"rpcUrl": "http://fresh:8545", "chainId": 1, "treasury": "new"}))
    (fresh / "chain_context.json").symlink_to(context)
    (trial / "verifier" / context_file).write_text(json.dumps({"treasury": "saved", "rpcUrl": "http://old:8545", "owner": "check-wallet"}))
    output = tmp_path / "verifier"
    installs = []

    def install(command, **kwargs):
        assert kwargs["env"]["CI"] == "true"
        installs.append((command, str(kwargs["cwd"]), (fresh / "pnpm-lock.yaml").read_text(),
                         json.loads((fresh / "package.json").read_text())))
        (fresh / "node_modules/added.txt").write_text("1.2.3")

    monkeypatch.setattr(subprocess, "run", install)

    class Environment:
        async def service_exec(self, command, **kwargs):
            assert kwargs == {"service": "chain", "user": "root"}
            script = shlex.split(command)[2].replace("/chain/chain_context.json", str(context))
            exec(script, {})
            return SimpleNamespace(return_code=0, stdout="", stderr="")

        async def upload_dir(self, source_dir, target_dir):
            shutil.copytree(source_dir, tmp_path / "uploaded")

        async def upload_file(self, source_path, target_path):
            pass

        async def exec(self, command, **kwargs):
            script = shlex.split(command)[2]
            script = script.replace("/tmp/regrade-workspace", str(tmp_path / "uploaded"))
            script = script.replace("/workspace", str(fresh)).replace("/logs/verifier", str(output))
            exec(script, {})
            return SimpleNamespace(return_code=0, stdout="", stderr="")

    agent = SavedWorkAgent(logs_dir=tmp_path / "logs", trial=str(trial))
    asyncio.run(agent.run("Ignored instruction", Environment(), SimpleNamespace()))
    assert ((fresh / "app.txt").read_text(), (fresh / "starter.txt").exists(),
            (fresh / "chain_context.json").is_symlink(), (fresh / "node_modules/added.txt").read_text()) == (
        "Saved page.", False, True, "1.2.3")
    assert installs == [(["pnpm", "install", "--frozen-lockfile"], str(fresh), "saved-lockfile", {"dependencies": {"added": "1.2.3"}})]
    assert json.loads(context.read_text()) == json.loads((output / "chain_context.json").read_text()) == {
        "rpcUrl": "http://fresh:8545", "chainId": 1, "treasury": "saved"}


def test_page_regrade_uses_normal_job_and_folds_checks_without_changing_model_fields(tmp_path, monkeypatch):
    from harbor.job import Job
    from ethevals import jobs
    task, config, row = saved_page(tmp_path)
    row.update(model_cost_usd=4.25, trajectory_url="https://example.org/original.json")
    (task / "tests/test.sh").write_text("Changed checks.\n")
    report = budget_check(plan([task], config, [row], n_attempts=1, saved_work=tmp_path / "cache"), 0)
    seen = []

    async def create(job_config):
        seen.append(job_config)

        class RecordedJob:
            async def run(self):
                destination = job_config.jobs_dir / job_config.job_name / "page__saved"
                recorded_trial(destination, task)
                (destination / "verifier/reward.json").write_text('{"reward": 0.0}')
                (destination / "verifier/reward-details.json").write_text(json.dumps({"reward": {
                    "kind": "programmatic", "score": 0, "criteria": [{"name": "page", "value": 0, "reasoning": "New check."}]}}))
                result = json.loads((destination / "result.json").read_text())
                result["verifier_result"]["rewards"] = {"reward": 0.0}
                (destination / "result.json").write_text(json.dumps(result))
        return RecordedJob()

    monkeypatch.setattr(Job, "create", create)
    monkeypatch.setattr(jobs, "check_credentials", lambda *args: pytest.fail("A regrade needs no agent credentials."))
    output = tmp_path / "output"
    assert asyncio.run(run(report, config, output, [row])) is True
    new, = read_rows(output / "rows.jsonl")
    assert (new["status"], new["checks"], new["checks_hash"], new["checks_generation"], new["regraded_at"]) == (
        "failed", {"page": {"passed": False, "reason": "New check."}},
        report["regrades"][0]["checks_hash"], 1, "2026-10-21T16:29:22.373811Z")
    assert {key: new[key] for key in row if key not in {
        "checks_hash", "checks_inputs", "checks_generation", "status", "checks", "rewards", "verifier_files", "verifier_url",
        "trajectory_file", "trajectory_download_url", "regraded_at", "error_kind", "error_reason", "no_answer"}} == {
        key: value for key, value in row.items() if key not in {
            "checks_hash", "checks_inputs", "checks_generation", "status", "checks", "rewards", "verifier_files", "verifier_url",
            "trajectory_file", "trajectory_download_url", "regraded_at", "error_kind", "error_reason", "no_answer"}}
    assert [(agent.name, agent.import_path, agent.kwargs) for agent in seen[0].agents] == [
        (None, "ethevals.saved_agent:SavedWorkAgent", {"trial": report["regrades"][0]["saved_work"]["trial"]})]
    assert ([entry.path for entry in seen[0].tasks], seen[0].environment.type) == ([task.resolve()], "docker")


def test_ci_schedules_eighteen_page_regrades_as_eighteen_jobs(tmp_path):
    from support import cli
    task, config, row = saved_page(tmp_path)
    config_path = tmp_path / "job.json"
    rows = tmp_path / "rows.jsonl"
    write_rows(rows, [{**row, "trial": number} for number in range(1, 19)])
    (task / "tests/test.sh").write_text("Changed checks.\n")
    output = tmp_path / "plan"
    emitted = tmp_path / "github-output"
    result = cli(Path(__file__).resolve().parents[2] / "scripts/ci.py", "plan-trials", "--config", config_path,
                 "--tasks", task, "--n-attempts", 18, "--rows", rows, "--budget", 1,
                 "--output", output, "--github-output", emitted)
    assert result.returncode == 0, result.stdout + result.stderr
    batches = json.loads((output / "regrades.json").read_text())
    assert [(batch["missing_trials"], [item["trial"] for item in batch["regrades"]]) for batch in batches] == [
        (0, [number]) for number in range(1, 19)]
    values = dict(line.split("=", 1) for line in emitted.read_text().splitlines())
    assert json.loads(values["regrade_matrix"]) == {"include": [
        {"index": index, "task_id": "build/question", "judge": False, "workspace": True} for index in range(18)]}
