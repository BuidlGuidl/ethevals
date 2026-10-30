import json
from pathlib import Path

from support import cli, recorded_trial
import pytest


def job_config(tmp_path, paid_by="plan"):
    path = tmp_path / "job.json"
    path.write_text(json.dumps({
        "harbor_version": "0.24.0", "n_attempts": 2, "retry": {"max_retries": 1},
        "modes": ["internet"],
        "models": {"local": {"name": "local/model", "effort": "high"}},
        "agents": {"local": {"name": "nop", "version": "1.0.0", "model": "local",
                              "paid_by": paid_by, "cost_limit_usd": 3,
                              **({"required_env": ["OFFLINE_PLAN_TOKEN"],
                                  "env": {"OFFLINE_PLAN_TOKEN": "offline-plan-token"}} if paid_by == "plan" else {})}},
    }))
    return path


def task_folder(tmp_path):
    task = tmp_path / "tasks/concepts/question"
    for name in ["environment", "tests", "solution"]:
        (task / name).mkdir(parents=True)
    (task / "task.toml").write_text(
        'schema_version = "1.3"\n[task]\nname = "buidlguidl/question"\n'
        'description = "Check a reply."\n[metadata]\npillar = "concepts"\n'
        'modes = ["internet"]\n')
    (task / "instruction.md").write_text("Name a unit.\n")
    (task / "environment/Dockerfile").write_text("FROM debian:bookworm-slim\n")
    (task / "tests/test.sh").write_text("#!/bin/sh\nexit 0\n")
    (task / "solution/solve.sh").write_text("#!/bin/sh\nexit 0\n")
    return task


def test_catalog_hashes_every_real_task_with_harbors_package_digest(tmp_path):
    from harbor.publisher.packager import Packager
    from ethevals.jobs import write_catalog

    paths = sorted(path.parent for path in (Path(__file__).resolve().parents[2] / "tasks").glob("*/*/task.toml"))
    write_catalog(paths, tmp_path)
    entries = json.loads((tmp_path / "catalog.json").read_text())["tasks"]
    assert len(entries) == len(paths)
    assert [entry["hash"] for entry in entries] == [
        "sha256:" + Packager.compute_content_hash(path)[0] for path in paths]


def test_catalog_lists_the_jobs_model_names(tmp_path):
    from ethevals.job_config import load_job
    from ethevals.jobs import write_catalog

    write_catalog([task_folder(tmp_path)], tmp_path / "catalog")
    catalog = json.loads((tmp_path / "catalog/catalog.json").read_text())
    assert catalog["models"] == [model.name for model in load_job().models.values()]
    assert catalog["n_attempts"] == load_job().n_attempts


@pytest.mark.parametrize("pillar", ["security", "transactions", "building"])
def test_catalog_refuses_removed_pillars(tmp_path, pillar):
    task = task_folder(tmp_path)
    settings = task / "task.toml"
    settings.write_text(settings.read_text().replace('pillar = "concepts"', f'pillar = "{pillar}"'))
    renamed = task.parent.parent / pillar / task.name
    renamed.parent.mkdir()
    task.rename(renamed)
    result = cli("-m", "ethevals.cli", "catalog", "--tasks", renamed, "--output", tmp_path / "catalog")
    assert result.returncode == 2
    assert "metadata.pillar must name a board pillar" in result.stderr


def test_row_builder_refuses_a_saved_trial_with_a_different_lock_digest(tmp_path):
    import shutil
    from ethevals.trial_rows import results_row

    folder = tmp_path / "trial"
    shutil.copytree(Path(__file__).parent / "fixtures/harbor/recorded-trial", folder)
    metadata = json.loads((folder / "board.json").read_text())
    lock = {"task": {"name": "buidlguidl/question", "type": "local", "digest": "sha256:" + "0" * 64}}
    (folder / "lock.json").write_text(json.dumps(lock))
    with pytest.raises(ValueError, match="task digest differs from the plan"):
        results_row(folder, metadata)


def test_board_job_uses_harbor_timeouts_without_overrides(tmp_path, monkeypatch):
    import asyncio
    from harbor.job import Job
    from ethevals.job_config import load_job
    from ethevals.jobs import budget_check, plan, run

    config, task = load_job(job_config(tmp_path, "free")), task_folder(tmp_path)
    report = budget_check(plan([task], config, [], n_attempts=1), 0)
    assert "time_limit" not in report["missing"][0]

    class Planned(Exception):
        pass

    async def capture(config):
        assert [(agent.name, agent.kwargs, agent.override_timeout_sec) for agent in config.agents] == [
            ("nop", {"version": "1.0.0", "reasoning_effort": "high"}, None)]
        assert ([item.path for item in config.tasks], config.verifier.override_timeout_sec) == ([task.resolve()], None)
        raise Planned

    monkeypatch.setattr(Job, "create", capture)
    with pytest.raises(Planned):
        asyncio.run(run(report, config, tmp_path / "out", []))


def test_run_forwards_the_agent_setup_timeout_multiplier(tmp_path, monkeypatch):
    import asyncio
    from harbor.job import Job
    from ethevals.cli import parse_args
    from ethevals.job_config import load_job
    from ethevals.jobs import budget_check, plan, run

    assert parse_args(["run", "--agent-setup-timeout-multiplier", "4"])[1].agent_setup_timeout_multiplier == 4.0
    with pytest.raises(SystemExit):
        parse_args(["run", "--agent-setup-timeout-multiplier", "0"])

    config, task = load_job(job_config(tmp_path, "free")), task_folder(tmp_path)
    report = budget_check(plan([task], config, [], n_attempts=1), 0)

    class Planned(Exception):
        pass

    seen = []

    async def capture(config):
        seen.append(config.agent_setup_timeout_multiplier)
        raise Planned

    monkeypatch.setattr(Job, "create", capture)
    with pytest.raises(Planned):
        asyncio.run(run(report, config, tmp_path / "default", []))
    with pytest.raises(Planned):
        asyncio.run(run(report, config, tmp_path / "slow", [], agent_setup_timeout_multiplier=4))
    assert seen == [None, 4]


def test_run_uploads_a_readable_copy_of_each_credential_file(tmp_path, monkeypatch):
    import asyncio
    import os
    import stat
    from harbor.job import Job
    from ethevals.job_config import load_job
    from ethevals.jobs import budget_check, plan, run

    path = job_config(tmp_path, "plan")
    data = json.loads(path.read_text())
    data["agents"]["local"]["required_files"] = [{"path": "${AUTH_PATH:-~/.codex/auth.json}", "policy": "plan_tokens"}]
    path.write_text(json.dumps(data))
    # Codex writes its own auth.json with mode 0600; Harbor copies it into the task as root and keeps the mode.
    auth = tmp_path / "auth.json"
    auth.write_text(json.dumps({"auth_mode": "chatgpt", "tokens": {"access_token": "offline-plan-token"}}))
    auth.chmod(0o600)
    monkeypatch.setenv("AUTH_PATH", str(auth))
    config, task = load_job(path), task_folder(tmp_path)
    report = budget_check(plan([task], config, [], n_attempts=1), 0)

    class Planned(Exception):
        pass

    seen = []

    async def capture(config):
        copy = Path(os.environ["AUTH_PATH"])
        seen.append((copy, copy.read_text(), stat.S_IMODE(copy.stat().st_mode), stat.S_IMODE(copy.parent.stat().st_mode),
                     config.agents[0].env.get("AUTH_PATH")))
        raise Planned

    monkeypatch.setattr(Job, "create", capture)
    with pytest.raises(Planned):
        asyncio.run(run(report, config, tmp_path / "out", []))
    copy, text, mode, parent_mode, agent_env = seen[0]
    assert copy != auth and text == auth.read_text() and mode == 0o644 and parent_mode == 0o700
    assert agent_env is None and not copy.exists() and os.environ["AUTH_PATH"] == str(auth)
    assert stat.S_IMODE(auth.stat().st_mode) == 0o600

    # An agent env that fixes the variable outranks the host env in Harbor, so the copy goes there too.
    config.agents["local"].env["AUTH_PATH"] = str(auth)
    with pytest.raises(Planned):
        asyncio.run(run(report, config, tmp_path / "fixed", []))
    copy, text, mode, _, agent_env = seen[1]
    assert agent_env == str(copy) and copy != auth and text == auth.read_text() and mode == 0o644


def test_opencode_gets_the_model_effort_as_its_variant(tmp_path, monkeypatch):
    import asyncio
    from harbor.job import Job
    from ethevals.job_config import load_job
    from ethevals.jobs import budget_check, plan, run

    path, task = job_config(tmp_path, "free"), task_folder(tmp_path)
    data = json.loads(path.read_text())
    data["agents"]["local"].update(name="opencode", version="1.18.33")
    path.write_text(json.dumps(data))
    config = load_job(path)
    report = budget_check(plan([task], config, [], n_attempts=1), 0)

    class Planned(Exception):
        pass

    async def capture(config):
        # OpenCode has no reasoning_effort option; its variant sets the provider's effort.
        assert [agent.kwargs for agent in config.agents] == [{"version": "1.18.33", "variant": "high"}]
        raise Planned

    monkeypatch.setattr(Job, "create", capture)
    with pytest.raises(Planned):
        asyncio.run(run(report, config, tmp_path / "out", []))


def test_plan_reserves_no_agent_spend_for_a_plan_but_run_requires_budget(tmp_path):
    config, task = job_config(tmp_path), task_folder(tmp_path)
    args = ["--config", config, "--tasks", task, "--output", tmp_path / "out",
            "--rows", tmp_path / "missing.jsonl"]
    planned = cli("-m", "ethevals.cli", "plan", *args)
    assert planned.returncode == 0, planned.stderr
    report = json.loads(planned.stdout)
    assert [(row["trial"], row["retry"], row["agent_reserve_usd"]) for row in report["missing"]] == [
        (1, 0, 0), (2, 0, 0)]
    assert report["worst_case_usd"] == 0
    refused = cli("-m", "ethevals.cli", "run", *args)
    assert refused.returncode == 2
    assert "requires --budget" in refused.stderr
    assert not (tmp_path / "out/jobs").exists()


def test_vanilla_plans_only_declared_tasks_and_configured_models(tmp_path):
    config, task = job_config(tmp_path, "api_key"), task_folder(tmp_path)
    data = json.loads(config.read_text())
    data["modes"] = ["vanilla", "internet"]
    data["agents"]["bare"] = {**data["agents"]["local"],
                              "name": "ethevals.vanilla:VanillaAgent", "modes": ["vanilla"]}
    config.write_text(json.dumps(data))
    quiz = tmp_path / "tasks/concepts/quiz"
    import shutil
    shutil.copytree(task, quiz)
    settings = quiz / "task.toml"
    settings.write_text(settings.read_text().replace('["internet"]', '["vanilla", "internet"]')
                        .replace('buidlguidl/question', 'buidlguidl/quiz'))
    args = ["--config", config, "--tasks", task, quiz, "--n-attempts", 1,
            "--output", tmp_path / "out", "--rows", tmp_path / "none"]
    result = cli("-m", "ethevals.cli", "plan", *args)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert [(row["task_id"], row["agent_key"], row["mode"], row["model"])
            for row in report["missing"]] == [
        ("concepts/question", "local", "internet", "local/model"),
        ("concepts/quiz", "local", "internet", "local/model"),
        ("concepts/quiz", "bare", "vanilla", "local/model")]
    assert report["worst_case_usd"] == 18
    selected = cli("-m", "ethevals.cli", "plan", *args, "--agents", "bare", "--modes", "vanilla")
    assert selected.returncode == 0, selected.stderr
    assert [(row["task_id"], row["paid_by"]) for row in json.loads(selected.stdout)["missing"]] == [
        ("concepts/quiz", "api_key")]


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


def test_recovery_skips_unreadable_metadata_and_keeps_current_trials(tmp_path):
    import shutil
    from ethevals.trial_rows import recover_rows

    fixture = Path(__file__).parent / "fixtures/harbor/recorded-trial"
    for name in ("current", "unreadable"):
        job = tmp_path / "jobs" / name
        shutil.copytree(fixture, job / "trial")
        metadata = json.loads((fixture / "board.json").read_text())
        if name == "unreadable":
            del metadata["retry"]
        (job / "board.json").write_text(json.dumps(metadata))
    rows = recover_rows(tmp_path)
    assert [(row["task_id"], row["retry"], row["status"]) for row in rows] == [
        ("concepts/question", 0, "passed")]


def test_skill_edits_repeat_only_skills_trials(tmp_path, monkeypatch):
    import asyncio
    from ethevals.job_config import load_job
    from ethevals.jobs import budget_check, plan, run

    config, task = load_job(job_config(tmp_path, "free")), task_folder(tmp_path)
    config.modes = ["vanilla", "internet", "skills"]
    config.agents["local"].modes = ["internet", "skills"]
    config.agents["bare"] = config.agents["local"].model_copy(update={"modes": ["vanilla"]})
    settings = task / "task.toml"
    settings.write_text(settings.read_text().replace('["internet"]', '["vanilla", "internet", "skills"]'))
    skill = tmp_path / "skills/units/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("---\nname: units\ndescription: Units.\n---\nOne metre.\n")
    monkeypatch.setattr("ethevals.skills.PACK", skill.parent.parent)
    report = plan([task], config, [], n_attempts=1)
    before = report["missing"]
    assert [(row["mode"], row["skills_hash"] is not None) for row in before] == [
        ("internet", False), ("skills", True), ("vanilla", False)]
    previous = [{**row, "status": "passed"} for row in before]
    assert plan([task], config, previous, n_attempts=1)["missing_trials"] == 0
    skill.write_text(skill.read_text().replace("One metre.", "Two metres."))
    after = plan([task], config, previous, n_attempts=1)["missing"]
    assert [(row["mode"], row["trial"], row["retry"]) for row in after] == [("skills", 1, 0)]
    assert after[0]["task_hash"] == before[1]["task_hash"]
    assert after[0]["skills_hash"] != before[1]["skills_hash"]
    with pytest.raises(ValueError, match="The skills pack differs from the plan"):
        asyncio.run(run(budget_check(report, 0), config, tmp_path / "out", []))
    assert not (tmp_path / "out/jobs").exists()


def test_published_trajectory_enriches_the_same_attempt_and_a_later_error_stays_latest():
    from ethevals.trial_rows import fold_rows, results_row

    folder = Path(__file__).parent / "fixtures/harbor/recorded-trial"
    row = results_row(folder, json.loads((folder / "board.json").read_text()))
    published = {**row, "trajectory_url": "https://example.org/trajectory.json"}
    assert fold_rows([row], [published])[0]["trajectory_url"] == "https://example.org/trajectory.json"
    assert fold_rows([published], [row])[0]["trajectory_url"] == "https://example.org/trajectory.json"
    later = {**row, "retry": 1, "status": "error", "error_kind": "execution", "error_reason": "Agent stopped."}
    assert [(item["retry"], item["status"]) for item in fold_rows([published], [later])] == [(1, "error")]


def test_planner_recovers_finished_trials_and_repeats_changed_tasks(tmp_path):
    import shutil
    from ethevals.job_config import load_job
    from ethevals.jobs import plan, task_entry
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
    assert [(row["trial"], row["retry"]) for row in pending["missing"]] == [(2, 0)]
    (task / "instruction.md").write_text("Name a different unit.\n")
    assert [(row["trial"], row["retry"]) for row in plan([task], config, prior)["missing"]] == [(1, 0), (2, 0)]


def test_api_key_budget_reserves_remaining_executions_and_retains_exhausted_errors(tmp_path):
    from ethevals.job_config import load_job
    from ethevals.jobs import budget_check, plan

    config, task = load_job(job_config(tmp_path, "api_key")), task_folder(tmp_path)
    missing = plan([task], config, [])["missing"]
    previous = [{**row, "status": "error", "retry": index} for index, row in enumerate(missing)]
    report = budget_check(plan([task], config, previous), 2)
    assert [(row["trial"], row["retry"], row["remaining_executions"], row["worst_case_usd"])
            for row in report["missing"]] == [(1, 1, 1, 3)]
    assert [(row["trial"], row["retry"]) for row in report["exhausted_errors"]] == [(2, 1)]
    assert (report["worst_case_usd"], report["within_budget"]) == (3, False)


@pytest.mark.parametrize("exception", ["AgentAuthenticationError", "RewardFileNotFoundError", "AgentTimeoutError", "ConnectionError"])
def test_retry_planning_uses_harbor_exclusions_and_stops_at_the_retry_limit(tmp_path, exception):
    import shutil
    from ethevals.job_config import load_job
    from ethevals.jobs import plan
    from ethevals.trial_rows import results_row

    config, task = load_job(job_config(tmp_path, "api_key")), task_folder(tmp_path)
    item = plan([task], config, [], n_attempts=1)["missing"][0]
    folder = tmp_path / "saved"
    shutil.copytree(Path(__file__).parent / "fixtures/harbor/recorded-trial", folder)
    result_path = folder / "result.json"
    result = json.loads(result_path.read_text())
    result["exception_info"] = {
        "exception_type": exception, "exception_message": "The agent failed.",
        "exception_traceback": "", "occurred_at": result["finished_at"],
    }
    result["verifier_result"] = None
    result_path.write_text(json.dumps(result))
    (folder / "verifier/reward.json").unlink()
    saved = results_row(folder, item)
    assert (saved["status"], saved["error_kind"], saved["retry"]) == ("error", exception, 0)
    report = plan([task], config, [saved], n_attempts=1)
    if exception == "ConnectionError":
        assert [(row["trial"], row["retry"], row["worst_case_usd"])
                for row in report["missing"]] == [(1, 1, 3)]
        saved["retry"] = 1
        report = plan([task], config, [saved], n_attempts=1)
    assert (report["missing"], report["exhausted_errors"], report["worst_case_usd"]) == ([], [saved], 0)


@pytest.mark.parametrize("partial", ["", '{"job_name":'])
@pytest.mark.parametrize("real_trial", [False, pytest.param(True, marks=pytest.mark.docker)])
def test_recovery_restarts_a_job_interrupted_during_its_first_config_write(tmp_path, monkeypatch, partial, real_trial):
    import asyncio
    import shutil
    from harbor.job import Job
    from ethevals.job_config import load_job
    from ethevals.jobs import budget_check, plan, run

    config = load_job(job_config(tmp_path, "free"))
    task = tmp_path / "concepts/question"
    shutil.copytree(Path(__file__).parent / "fixtures/harbor/concepts/question", task)
    config.agents["local"].name = "oracle"
    report = budget_check(plan([task], config, [], n_attempts=1), 0)
    output = tmp_path / "out"

    async def interrupted(job):
        (job.job_dir / "config.json").write_text(partial)
        raise RuntimeError("Stopped during the first config write.")

    original_run = Job.run
    monkeypatch.setattr(Job, "run", interrupted)
    with pytest.raises(RuntimeError, match="Stopped during the first config write"):
        asyncio.run(run(report, config, output, []))
    job_folder = next((output / "jobs").iterdir())
    assert (job_folder / "config.json").read_text() == partial

    async def finished(job):
        recorded_trial(job.job_dir / "trial", task)

    monkeypatch.setattr(Job, "run", original_run if real_trial else finished)
    assert asyncio.run(run(report, config, output, [])) is True
    row = json.loads((output / "rows.jsonl").read_text())
    assert (row["trial"], row["retry"], row["status"]) == (1, 0, "passed")
    assert len(list((output / "jobs").glob("*/*/result.json"))) == 1


def test_execution_rejects_task_edits_after_admission(tmp_path):
    import asyncio
    from ethevals.job_config import load_job
    from ethevals.jobs import budget_check, plan, run

    config, task = load_job(job_config(tmp_path, "free")), task_folder(tmp_path)
    report = budget_check(plan([task], config, [], n_attempts=1), 0)
    (task / "instruction.md").write_text("Name a different unit.\n")
    with pytest.raises(ValueError, match="The task differs from the plan"):
        asyncio.run(run(report, config, tmp_path / "out", []))
    assert not (tmp_path / "out/jobs").exists()


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
    from harbor.publisher.packager import Packager
    task = task_folder(tmp_path)
    (task / "tests/private.txt").write_text("Do not publish the verifier in the catalog.")
    output = tmp_path / "catalog"
    result = cli("-m", "ethevals.cli", "catalog", "--tasks", task, "--output", output)
    assert result.returncode == 0, result.stderr
    catalog = json.loads((output / "catalog.json").read_text())
    entry = catalog["tasks"][0]
    assert {key: value for key, value in entry.items() if key != "hash"} == {
        "id": "concepts/question", "pillar": "concepts", "area": None, "layer": None,
        "name": "buidlguidl/question", "description": "Check a reply.",
        "instruction": "Name a unit.\n", "modes": ["internet"]}
    assert entry["hash"] == "sha256:" + Packager.compute_content_hash(task)[0]


def test_catalog_carries_the_task_area(tmp_path):
    task = task_folder(tmp_path)
    settings = task / "task.toml"
    settings.write_text(settings.read_text().replace('pillar = "concepts"', 'pillar = "concepts"\narea = "Tokens"'))
    output = tmp_path / "catalog"
    result = cli("-m", "ethevals.cli", "catalog", "--tasks", task, "--output", output)
    assert result.returncode == 0, result.stderr
    entry = json.loads((output / "catalog.json").read_text())["tasks"][0]
    assert (entry["id"], entry["area"]) == ("concepts/question", "Tokens")


def build_task_folder(tmp_path, layer):
    task = task_folder(tmp_path)
    build = task.parent.parent / "build/question"
    build.parent.mkdir()
    task.rename(build)
    settings = build / "task.toml"
    settings.write_text(settings.read_text().replace('pillar = "concepts"', f'pillar = "build"\nlayer = {layer}'))
    return build


def test_catalog_carries_a_build_tasks_layer(tmp_path):
    task = build_task_folder(tmp_path, '"frontend"')
    output = tmp_path / "catalog"
    result = cli("-m", "ethevals.cli", "catalog", "--tasks", task, "--output", output)
    assert result.returncode == 0, result.stderr
    entry = json.loads((output / "catalog.json").read_text())["tasks"][0]
    assert (entry["id"], entry["layer"]) == ("build/question", "frontend")


@pytest.mark.parametrize("layer", ['"pages"', '""', '["contracts"]'])
def test_task_lint_refuses_an_unknown_layer(tmp_path, layer):
    result = cli("-m", "ethevals.cli", "lint", "--tasks", build_task_folder(tmp_path, layer))
    assert result.returncode == 2
    assert "metadata.layer must be contracts, frontend, or backend, on a build task" in result.stderr


def test_task_lint_refuses_a_layer_outside_build(tmp_path):
    task = task_folder(tmp_path)
    settings = task / "task.toml"
    settings.write_text(settings.read_text().replace('pillar = "concepts"', 'pillar = "concepts"\nlayer = "contracts"'))
    result = cli("-m", "ethevals.cli", "lint", "--tasks", task)
    assert result.returncode == 2
    assert "metadata.layer must be contracts, frontend, or backend, on a build task" in result.stderr


@pytest.mark.parametrize("area", ['""', '"   "', "42", "true", '[]'])
def test_task_lint_refuses_an_empty_or_non_string_area(tmp_path, area):
    task = task_folder(tmp_path)
    settings = task / "task.toml"
    settings.write_text(settings.read_text().replace('pillar = "concepts"', f'pillar = "concepts"\narea = {area}'))
    result = cli("-m", "ethevals.cli", "lint", "--tasks", task)
    assert result.returncode == 2
    assert "metadata.area must be a nonempty string" in result.stderr


@pytest.mark.parametrize("command", ["lint", "catalog", "plan", "export-hf"])
def test_task_package_names_must_be_unique(tmp_path, command):
    import shutil

    task = task_folder(tmp_path)
    other = task.with_name("other")
    shutil.copytree(task, other)
    args = ["--tasks", task, other]
    if command != "lint":
        args.extend(["--output", tmp_path / "out"])
    if command == "plan":
        args.extend(["--config", job_config(tmp_path)])
    result = cli("-m", "ethevals.cli", command, *args)
    assert result.returncode == 2
    assert "Duplicate task name: buidlguidl/question" in result.stderr
    if command == "export-hf":
        assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("details", [
    {"reward": {"criteria": [{"name": "unit", "value": "true", "reasoning": "Matches."}]}},
    {"reward": {"criteria": [{"name": " ", "value": 1, "reasoning": "Matches."}]}},
    {},
])
def test_invalid_rewardkit_details_become_verification_errors(tmp_path, details):
    import shutil
    from ethevals.trial_rows import results_row

    fixture = Path(__file__).parent / "fixtures/harbor/recorded-trial"
    shutil.copytree(fixture, tmp_path / "trial")
    metadata = json.loads((fixture / "board.json").read_text())
    path = tmp_path / "trial/verifier/reward-details.json"
    path.write_text(json.dumps(details))
    row = results_row(tmp_path / "trial", metadata)
    assert (row["status"], row["error_kind"], row["checks"]) == ("error", "verification", {})
    assert str(path) in row["error_reason"]


@pytest.mark.parametrize("phase,status", [("Agent", "passed"), ("Verifier", "error")])
def test_saved_timeout_keeps_its_limit_without_the_source_task(tmp_path, phase, status):
    import shutil
    from ethevals.trial_rows import results_row

    fixture = Path(__file__).parent / "fixtures/harbor/recorded-trial"
    folder = tmp_path / "trial"
    shutil.copytree(fixture, folder)
    metadata = json.loads((fixture / "board.json").read_text())
    result_path = folder / "result.json"
    result = json.loads(result_path.read_text())
    message = f"{phase} execution timed out after 2.5 seconds"
    result["exception_info"] = {
        "exception_type": f"{phase}TimeoutError", "exception_message": message,
        "exception_traceback": "", "occurred_at": result["finished_at"],
    }
    result["config"]["task"]["path"] = str(tmp_path / "removed-task")
    if phase == "Verifier":
        result["verifier_result"] = None
        (folder / "verifier/reward.json").unlink()
    result_path.write_text(json.dumps(result))
    row = results_row(folder, metadata)
    assert (row["status"], row["limit"]) == (status, {"type": "time", "limit": 2.5, "reason": message})
    assert "time_limit" not in row


@pytest.mark.docker
@pytest.mark.parametrize("paid_by", ["api_key", "plan"])
def test_any_configured_agent_keeps_api_price_cost_when_a_plan_or_key_pays(tmp_path, monkeypatch, paid_by):
    import os
    import shutil

    config = job_config(tmp_path, paid_by)
    data = json.loads(config.read_text())
    data["agents"]["local"]["name"] = "local_agent:LocalAgent"
    data["agents"]["local"]["kwargs"] = {"delay": 6}
    config.write_text(json.dumps(data))
    fixture = Path(__file__).parent / "fixtures/harbor"
    task = tmp_path / "concepts/question"
    shutil.copytree(fixture / "concepts/question", task)
    settings = task / "task.toml"
    settings.write_text(settings.read_text() + "\n[agent]\ntimeout_sec = 5\n")
    monkeypatch.setenv("PYTHONPATH", str(fixture.resolve()) + os.pathsep + os.environ.get("PYTHONPATH", ""))
    result = cli("-m", "ethevals.cli", "run", "--config", config, "--tasks", task,
                 "--trial", 2, "--budget", 6 if paid_by == "api_key" else 0,
                 "--output", tmp_path / "out", "--rows", tmp_path / "none")
    assert result.returncode == 0, result.stdout + result.stderr
    row = json.loads((tmp_path / "out/rows.jsonl").read_text())
    assert (row["trial"], row["status"], row["model_cost_usd"], row["total_tokens"], row["paid_by"]) == (
        2, "passed", 0.01234, 110, paid_by)
    assert row["limit"]["type"] == "time"
    assert row["limit"]["limit"] == 5
    assert row["limit"]["reason"] == "Agent execution timed out after 5.0 seconds"
    assert "time_limit" not in row
    trial_config = json.loads(next((tmp_path / "out/jobs").glob("*/*/config.json")).read_text())
    assert trial_config["agent"]["kwargs"] == {"delay": 6, "version": "1.0.0", "reasoning_effort": "high"}
    assert (trial_config["agent"].get("override_timeout_sec"),
            trial_config.get("verifier", {}).get("override_timeout_sec")) == (None, None)


@pytest.mark.docker
@pytest.mark.parametrize("skills_dir", [None, "/opt/task-skills"])
def test_skills_trial_loads_captured_pack_through_harbor(tmp_path, monkeypatch, skills_dir):
    import asyncio
    import shutil
    from ethevals.job_config import load_job
    from ethevals.jobs import budget_check, plan, run
    from ethevals.skills import pack_skills
    from ethevals.trial_rows import previous_rows

    fixture = Path(__file__).parent / "fixtures/harbor"
    monkeypatch.syspath_prepend(str(fixture.resolve()))
    task = tmp_path / "concepts/question"
    shutil.copytree(fixture / "concepts/question", task)
    settings = task / "task.toml"
    settings.write_text(settings.read_text().replace('["internet"]', '["internet", "skills"]'))
    if skills_dir:
        with settings.open("a") as file:
            file.write(f'skills_dir = "{skills_dir}"\n')
    config = load_job(job_config(tmp_path, "free"))
    config.modes = config.agents["local"].modes = ["internet", "skills"]
    config.agents["local"].name = "local_agent:SkillsAgent"
    captured = pack_skills()
    report = budget_check(plan([task], config, [], n_attempts=1, skills_pack=captured), 0)
    # A live pack edit after planning cannot change the bytes that Harbor receives.
    changed = tmp_path / "changed-skills/units/SKILL.md"
    changed.parent.mkdir(parents=True)
    changed.write_text("---\nname: units\ndescription: Changed.\n---\nDifferent bytes.\n")
    monkeypatch.setattr("ethevals.skills.PACK", changed.parent.parent)
    output = tmp_path / "out"
    assert asyncio.run(run(report, config, output, [], skills_pack=captured)) is True
    rows = previous_rows(output, tmp_path / "none")
    assert [(row["mode"], row["status"], row["skills_hash"]) for row in rows] == [
        ("internet", "passed", None), ("skills", "passed", captured.hash)]
    expected = {name.removeprefix("/skills/"): data.hex() for name, data in captured.files.items()}
    for row in rows:
        trial = Path(row["trajectory_file"]).parent.parent
        proof = json.loads((trial / "agent/skills.json").read_text())
        saved = json.loads((trial / "config.json").read_text())
        if row["mode"] == "skills":
            assert proof == {"directory": skills_dir or "/harbor/skills", "files": expected}
            assert saved["agent"]["skills"] == [str((output / "skills" / captured.hash).resolve())]
        else:
            assert proof == {"directory": skills_dir, "files": {}}
            assert saved["agent"].get("skills", []) == []
    assert plan([task], config, rows, n_attempts=1, skills_pack=captured)["missing_trials"] == 0
    assert [(item["mode"], item["retry"]) for item in plan([task], config, rows, n_attempts=1)["missing"]] == [
        ("skills", 0)]


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
    task = Path(__file__).parent / "fixtures/harbor/concepts/question"
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
    assert [(row["trial"], row["retry"], row["status"]) for row in rows] == [(1, 0, "passed"), (2, 0, "passed")]


@pytest.mark.docker
def test_cli_runs_a_real_oracle_and_recovers_rows_without_repeating_finished_trials(tmp_path):
    import shutil

    config = job_config(tmp_path, "free")
    data = json.loads(config.read_text())
    data["agents"]["local"]["name"] = "oracle"
    data["n_attempts"] = 1
    config.write_text(json.dumps(data))
    task = Path(__file__).parent / "fixtures/harbor/concepts/question"
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
