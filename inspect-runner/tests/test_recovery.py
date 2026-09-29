"""Recover attempts from Inspect logs before starting another paid run."""
import argparse
import itertools
import json
from pathlib import Path
import subprocess

import pytest
from inspect_ai.log import read_eval_log, write_eval_log

from ethevals.actors import select_actors
from ethevals.config import load_config
from ethevals.loader import load_eval
from ethevals.planning import plan
from ethevals.rows import epoch_identity, fold_rows, previous_rows, read_rows, write_rows
from ethevals.runner import run
from test_ci import ci, ROOT


def quiz():
    config = load_config()
    return config, load_eval(ROOT / "evals/concepts/agent-registries", config)


def test_fold_is_order_independent_and_sorts_epochs_as_numbers():
    old = {"eval_id": "a", "eval_hash": "a", "epoch": 2, "attempt": 1, "status": "error", "completed_at": "2026-01-01"}
    later = {**old, "status": "passed", "completed_at": "2026-01-02"}
    last = {**later, "epoch": 10}
    for groups in itertools.permutations([[old], [later], [last]]):
        assert [(r["epoch"], r["status"]) for r in fold_rows(*groups)] == [(2, "passed"), (10, "passed")]


def test_runner_exception_after_eval_retains_rows_and_plan_reads_logs(tmp_path, monkeypatch):
    import ethevals.runner as runner
    config, evaluation = quiz()
    real_eval = runner.eval

    def interrupted(*args, **kwargs):
        real_eval(*args, **kwargs)
        raise RuntimeError("Runner failed after eval")

    monkeypatch.setattr(runner, "eval", interrupted)
    with pytest.raises(RuntimeError, match="after eval"):
        run([evaluation], config, tmp_path, answer="reference", epochs=1)
    row = read_rows(tmp_path / "rows.jsonl")[0]
    assert (row["status"], row["attempt"]) == ("passed", 1)
    (tmp_path / "rows.jsonl").unlink()
    players, _ = select_actors(config, answer="reference", planning=True)
    report = plan([evaluation], config, players, previous_rows(tmp_path), epochs=1).report
    assert (report["missing_epochs"], report["worst_case_usd"]) == (0, 0)


def test_timeout_artifact_rebuilds_attempts_and_failed_publication_keeps_record(tmp_path, monkeypatch):
    config, evaluation = quiz()
    output, rows = tmp_path / "run", tmp_path / "rows.jsonl"
    run([evaluation], config, output, answer="reference", epochs=2)
    logs = sorted((output / "logs").glob("*.eval"))
    log = read_eval_log(str(logs[1]))
    log.eval.metadata["attempt"] = 2
    log.samples = []
    write_eval_log(log, str(logs[1]))
    (output / "rows.jsonl").unlink()
    (output / "paid-started.json").write_text(json.dumps({"run_id": "12-1", "commit": "a" * 40}))
    persisted = []
    monkeypatch.setattr(ci, "commit_results", lambda rows, saved, *args: persisted.append((rows, saved)))

    def failed(*args, **kwargs):
        raise RuntimeError("Release upload failed")

    monkeypatch.setattr(ci, "publish_logs", failed)
    args = argparse.Namespace(output=output, repo="owner/repo", publish=True)
    assert ci.publish_artifacts(args) == 1
    assert sorted((r["status"], r["attempt"]) for r in persisted[0][0]) == [("error", 2), ("passed", 1)]
    assert persisted[0][1] == {"12-1": {"commit": "a" * 40}}
    players, _ = select_actors(config, answer="reference", planning=True)
    report = plan([evaluation], config, players, persisted[0][0], epochs=2).report
    assert (report["missing_epochs"], len(report["exhausted_errors"])) == (0, 1)


def test_publication_retry_uses_artifact_identity_and_gate_ignores_step_names(tmp_path, monkeypatch):
    import io
    import zipfile
    from datetime import datetime, timezone
    config, evaluation = quiz()
    output = tmp_path / "run"
    run([evaluation], config, output, answer="reference", epochs=1)
    marker = {"run_id": "12-1", "commit": "a" * 40}
    (output / "paid-started.json").write_text(json.dumps(marker))
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as contents:
        contents.writestr("results/ci-run/paid-started.json", json.dumps(marker))
    saved = {}
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "2")
    monkeypatch.setattr(ci, "stored_file", lambda ref, path: json.dumps(saved) if path == ci.RECEIPTS else "")
    artifact = {"id": 1, "name": "paid-12-1", "expired": False,
                "created_at": datetime.now(timezone.utc).isoformat()}
    queries = []

    def api(*args, **kwargs):
        assert not args[-1].endswith("/zip")
        queries.append(args[-1])
        return subprocess.CompletedProcess(args, 0, stdout=archive.getvalue() if args[-1].endswith("/zip")
                                           else json.dumps({"artifacts": [
                                               {**artifact, "id": 0, "created_at": "1900-01-01T00:00:00Z"}, artifact]}))

    monkeypatch.setattr(ci, "command", api)
    with pytest.raises(ValueError, match="12-1"):
        ci.require_recorded_runs("owner/repo")
    monkeypatch.setattr(ci, "commit_results", lambda rows, receipts, *args: saved.update(receipts))
    published = []

    def logs(output, repo, run_id, commit, **kwargs):
        published.append((run_id, commit))
        return {"rows_file": str(output / "rows.jsonl"), "assets": []}

    monkeypatch.setattr(ci, "publish_logs", logs)
    args = argparse.Namespace(output=output, repo="owner/repo", publish=True)
    assert ci.publish_artifacts(args) == 0
    ci.require_recorded_runs("owner/repo")
    assert saved == {"12-1": {"commit": "a" * 40}}
    assert published == [("12-1", "a" * 40)]
    assert all("/jobs" not in query and "/zip" not in query for query in queries)

    # A zero-work or gated artifact cannot create a receipt or PR.
    idle = tmp_path / "idle"
    idle.mkdir()
    args.output = idle
    assert ci.publish_artifacts(args) == 0
    assert saved == {"12-1": {"commit": "a" * 40}}
    assert published == [("12-1", "a" * 40)]


def test_paid_run_needs_budget_before_constructing_provider(tmp_path, monkeypatch):
    config, evaluation = quiz()
    monkeypatch.setenv("OPENROUTER_API_KEY", "inert-test-key")
    monkeypatch.setattr("ethevals.actors.model_actor", lambda *args: pytest.fail("Provider constructed"))
    with pytest.raises(ValueError, match="requires --budget"):
        run([evaluation], config, tmp_path, models=["opus"], epochs=1)
    with pytest.raises(ValueError, match="Budget exceeded"):
        run([evaluation], config, tmp_path, models=["opus"], epochs=1, budget=0)


def test_time_plan_only_runs_epochs_that_fit(tmp_path):
    config, evaluation = quiz()
    success, rows = run([evaluation], config, tmp_path, answer="reference", epochs=3, wall_seconds=1100)
    assert success
    assert [(r["epoch"], r["status"]) for r in rows] == [(1, "passed")]
    report = json.loads((tmp_path / "plan.json").read_text())
    assert report["reserved_wall_seconds"] == 1020 + report["preparation_seconds"]
    assert report["deferred_epochs"] == 2
    players, _ = select_actors(config, answer="reference", planning=True)
    assert [r["epoch"] for r in plan([evaluation], config, players, previous_rows(tmp_path), epochs=3).report["missing"]] == [2, 3]


def test_admission_counts_discovery_and_startup_and_interleaves_models():
    config, evaluation = quiz()
    config.max_tasks = config.max_samples = 2
    players, _ = select_actors(config, ["opus", "codex"], ["vanilla"], planning=True)
    report = plan([evaluation], config, players, [], epochs=3, wall_seconds=1700, preparation_seconds=100).report
    assert [(row["model"], row["epoch"]) for row in report["missing"]] == [
        ("openrouter/anthropic/claude-opus-5.5", 1), ("openrouter/openai/gpt-6-sol", 1)]
    assert (report["reserved_wall_seconds"], report["deferred_epochs"]) == (1630, 4)
    assert [row["epoch"] for row in report["missing"]] == [1, 1]
    internet, _ = select_actors(config, ["opus", "codex"], ["internet"], planning=True)
    report = plan([evaluation], config, internet, [], epochs=3, wall_seconds=3700, preparation_seconds=100).report
    assert (report["missing_epochs"], report["reserved_wall_seconds"], report["task_lifecycle_seconds"]) == (4, 3670, 120)


def test_deferred_long_epochs_keep_admission_balanced_across_models():
    from collections import Counter
    config = load_config()
    evals = [load_eval(path, config) for path in sorted((ROOT / "evals").glob("*/*"))]
    players, _ = select_actors(config, modes=["vanilla", "internet"], planning=True)
    report = plan(evals, config, players, [], wall_seconds=16200).report
    assert dict(Counter(row["model"] for row in report["missing"])) == {
        "openrouter/anthropic/claude-opus-5.5": 3, "openrouter/openai/gpt-6-sol": 3,
        "openrouter/moonshotai/kimi-k3": 3, "openrouter/z-ai/glm-5.3": 3}
    assert (report["missing_epochs"], report["reserved_wall_seconds"] ) == (12, 12240)
    assert {row["mode"] for row in report["missing"]} == {"vanilla"}


def test_run_executes_final_admission_without_selecting_again(tmp_path, monkeypatch):
    import ethevals.planning as planning
    import ethevals.runner as runner
    config, evaluation = quiz()
    config.max_tasks = config.max_samples = 2
    selection = planning.epoch_selection
    selected = 0

    def once(*args, **kwargs):
        nonlocal selected
        selected += 1
        assert selected == 1
        return selection(*args, **kwargs)

    monkeypatch.setattr(runner, "epoch_selection", once)
    monkeypatch.setattr(planning, "epoch_selection", lambda *args, **kwargs: pytest.fail("Plan selected work again"))
    from types import SimpleNamespace
    monkeypatch.setattr(runner, "time", SimpleNamespace(monotonic=iter([0, 100]).__next__))
    success, rows = run([evaluation], config, tmp_path, answer="reference", epochs=3, wall_seconds=1700)
    report = json.loads((tmp_path / "plan.json").read_text())
    assert success
    assert [(r["epoch"], r["status"]) for r in rows] == [(1, "passed"), (2, "passed")]
    assert [r["epoch"] for r in report["missing"]] == [1, 2]
    assert report["preparation_seconds"] == 100


def test_admitted_config_keys_keep_different_efforts_on_the_same_model(tmp_path, monkeypatch):
    config, evaluation = quiz()
    first = config.models["opus"].model_copy(update={"model": "mockllm/shared", "harness": None})
    config.models = {"high": first, "low": first.model_copy(update={"effort": "low"})}
    config.grader.model = "mockllm/grader"
    # Both providers are MockLLM. The gate key never reaches a provider request.
    monkeypatch.setenv("OPENROUTER_API_KEY", "inert-offline-gate-key")
    success, rows = run([evaluation], config, tmp_path, models=["high", "low"], modes=["vanilla"], epochs=1, budget=20)
    assert success
    assert [(row["effort"], row["status"], row["attempt"]) for row in rows] == [
        ("high", "failed", 1), ("low", "failed", 1)]


@pytest.mark.parametrize("mode", ["vanilla", "internet"])
def test_planned_identity_matches_every_configured_provider(monkeypatch, mode):
    config, evaluation = quiz()
    monkeypatch.setenv("OPENROUTER_API_KEY", "inert-test-key")
    for key, settings in config.models.items():
        planned, _ = select_actors(config, [key], [mode], planning=True)
        actual, _ = select_actors(config, [key], [mode])
        expected = (evaluation.id, evaluation.hash, settings.harness if mode == "internet" else None,
                    settings.model, settings.effort, mode, None, 1)
        for selection in (planned, actual):
            actor = selection(evaluation)[0][1]
            assert epoch_identity({"eval_id": evaluation.id, "eval_hash": evaluation.hash, "mode": mode,
                                   **actor.metadata}, 1) == expected


def test_late_publication_retains_current_source_and_newer_rows(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GH_TOKEN", "inert-test-token")
    monkeypatch.setattr(ci, "RECEIPTS", Path("results/runs.json"))
    ci.command("git", "init", "-b", "main", capture_output=True)
    ci.command("git", "config", "user.name", "Test")
    ci.command("git", "config", "user.email", "test@example.org")
    source = Path("source.txt")
    source.write_text("old source")
    rows = Path("results/rows.jsonl")
    old = {"eval_id": "a", "epoch": 1, "status": "error", "attempt": 1}
    write_rows(rows, [old])
    ci.command("git", "add", ".")
    ci.command("git", "commit", "-m", "Old source", capture_output=True)
    first = ci.command("git", "rev-parse", "HEAD", capture_output=True).stdout.strip()
    source.write_text("new source")
    newer = [{**old, "status": "passed", "attempt": 2}, {**old, "epoch": 2, "status": "passed"}]
    write_rows(rows, newer)
    ci.command("git", "add", ".")
    ci.command("git", "commit", "-m", "New source and rows", capture_output=True)
    latest = ci.command("git", "rev-parse", "HEAD", capture_output=True).stdout.strip()
    ci.command("git", "update-ref", "refs/remotes/origin/main", latest)
    ci.command("git", "update-ref", "refs/remotes/origin/ci/results", first)
    ci.command("git", "checkout", "--detach", first, capture_output=True)
    real_command, pushed = ci.command, []

    def local_only(*args, **kwargs):
        if args[:2] == ("git", "push"):
            pushed.append(args[3].split(":")[0])
            return subprocess.CompletedProcess(args, 0)
        if args[0] == "gh":
            return subprocess.CompletedProcess(args, 0, stdout="[]")
        return real_command(*args, **kwargs)

    monkeypatch.setattr(ci, "command", local_only)
    ci.commit_results(*ci.result_record(read_rows(rows)), "owner/repo", True)
    assert real_command("git", "show", f"{pushed[-1]}:source.txt", capture_output=True).stdout == "new source"
    assert ci.result_record()[0] == newer
    # Retrying the same old observation after a newer publication preserves both rows.
    write_rows(rows, [old])
    ci.commit_results(*ci.result_record(read_rows(rows)), "owner/repo", True)
    assert ci.result_record()[0] == newer
