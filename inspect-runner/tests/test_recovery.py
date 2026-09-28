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
    report = plan([evaluation], config, players, previous_rows(tmp_path), epochs=1)
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
    monkeypatch.setattr(ci, "RECEIPTS", tmp_path / "runs.json")
    monkeypatch.setattr(ci, "restore_results", lambda rows: None)
    persisted = []
    monkeypatch.setattr(ci, "results_pr", lambda rows, *args: persisted.append(read_rows(rows)))

    def failed(*args, **kwargs):
        raise RuntimeError("Release upload failed")

    monkeypatch.setattr(ci, "publish_logs", failed)
    args = argparse.Namespace(output=output, rows=rows, repo="owner/repo", run_id="12-1", commit="a" * 40,
                              publish=True, open_pr=True)
    with pytest.raises(RuntimeError, match="Release upload failed"):
        ci.publish_results(args, [evaluation])
    assert sorted((r["status"], r["attempt"]) for r in persisted[0]) == [("error", 2), ("passed", 1)]
    assert ci.receipts() == {"12-1": {"commit": "a" * 40}}
    players, _ = select_actors(config, answer="reference", planning=True)
    report = plan([evaluation], config, players, read_rows(rows), epochs=2)
    assert (report["missing_epochs"], len(report["exhausted_errors"])) == (0, 1)


def test_paid_run_refuses_unrecorded_earlier_work(tmp_path, monkeypatch):
    config, evaluation = quiz()
    monkeypatch.setenv("OPENROUTER_API_KEY", "inert-test-key")
    monkeypatch.setattr(ci, "RECEIPTS", tmp_path / "runs.json")
    history = [{"workflow_runs": [{"id": 12, "run_number": 4, "run_attempt": 2}]}]
    monkeypatch.setattr(ci, "command", lambda *a, **kw: subprocess.CompletedProcess(a, 0, stdout=json.dumps(history)))
    with pytest.raises(ValueError, match="12-1, 12-2"):
        run([evaluation], config, tmp_path / "run", models=["opus"], budget=100, epochs=1,
            before_paid=lambda: ci.require_recorded_runs("owner/repo", "13", "1"))
    ci.RECEIPTS.write_text(json.dumps({"12-1": {}, "12-2": {}}))
    ci.require_recorded_runs("owner/repo", "13", "1")
    assert json.loads((tmp_path / "run/plan.json").read_text())["within_budget"] is True


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
    success, rows = run([evaluation], config, tmp_path, answer="reference", epochs=3, wall_seconds=1200)
    assert success
    assert [(r["epoch"], r["status"]) for r in rows] == [(1, "passed")]
    report = json.loads((tmp_path / "plan.json").read_text())
    assert (report["reserved_wall_seconds"], report["deferred_epochs"]) == (1170, 2)
    players, _ = select_actors(config, answer="reference", planning=True)
    assert [r["epoch"] for r in plan([evaluation], config, players, previous_rows(tmp_path), epochs=3)["missing"]] == [2, 3]


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
    ci.results_pr(rows, "owner/repo", True)
    assert real_command("git", "show", f"{pushed[-1]}:source.txt", capture_output=True).stdout == "new source"
    assert read_rows(rows) == newer
    # Retrying the same old observation after a newer publication preserves both rows.
    write_rows(rows, [old])
    ci.results_pr(rows, "owner/repo", True)
    assert read_rows(rows) == newer
