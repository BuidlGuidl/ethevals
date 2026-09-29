"""Resume attempts and publish rows from Inspect logs."""
import argparse
import itertools
import json
from pathlib import Path
import subprocess

import pytest
from inspect_ai.log import read_eval_log, write_eval_log

from ethevals.actors import select_actors
from ethevals.config import Config
from support import load_config
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
    monkeypatch.delenv("PYTEST_CURRENT_TEST")
    config, evaluation = quiz()
    output = tmp_path / "eval-run-12-1"
    run([evaluation], config, output, answer="reference", epochs=2)
    logs = sorted((output / "logs").glob("*.eval"))
    log = read_eval_log(str(logs[1]))
    log.eval.metadata["attempt"] = 2
    log.samples = []
    write_eval_log(log, str(logs[1]))
    (output / "rows.jsonl").unlink()
    persisted = []
    monkeypatch.setattr(ci, "commit_results", lambda rows, *args: persisted.append(rows))

    def failed(*args, **kwargs):
        raise RuntimeError("Release upload failed")

    monkeypatch.setattr(ci, "publish_logs", failed)
    args = argparse.Namespace(output=tmp_path, repo="owner/repo", publish=True)
    assert ci.publish_artifacts(args) == 1
    assert sorted((r["status"], r["attempt"]) for r in persisted[0]) == [("error", 2), ("passed", 1)]
    players, _ = select_actors(config, answer="reference", planning=True)
    report = plan([evaluation], config, players, persisted[0], epochs=2).report
    assert (report["missing_epochs"], len(report["exhausted_errors"])) == (0, 1)


def test_paid_run_needs_budget_before_constructing_provider(tmp_path, monkeypatch):
    config, evaluation = quiz()
    monkeypatch.setenv("OPENROUTER_API_KEY", "inert-test-key")
    monkeypatch.setattr("ethevals.actors.model_actor", lambda *args: pytest.fail("Provider constructed"))
    with pytest.raises(ValueError, match="requires --budget"):
        run([evaluation], config, tmp_path, agents=["opus"], epochs=1)
    with pytest.raises(ValueError, match="Budget exceeded"):
        run([evaluation], config, tmp_path, agents=["opus"], epochs=1, budget=0)


def small_config():
    prices = dict(input=1, output=1, input_cache_read=1, input_cache_write=1)
    model = dict(model="mockllm/test", effort="high")
    return Config(epochs=3, time_limits={"quiz": 10, "build": 1200, "act": 1200}, cost_limit=2, max_attempts=2,
                  concurrency=1, search=False, prices={"mockllm/test": prices}, price_source="test",
                  grader={**model, "max_tokens": 10},
                  agents={"test": {**model, "harness": None}})


def test_admission_reaches_every_epoch():
    config = small_config()
    evals = [load_eval(ROOT / "evals/concepts" / name, config)
             for name in ("agent-registries", "wei-per-ether")]
    players, _ = select_actors(config, modes=["vanilla"], planning=True)
    recorded = []
    while True:
        report = plan(evals, config, players, recorded, wall_seconds=2600).report
        assert report["missing_epochs"] > 0
        recorded = fold_rows(recorded, [{**row, "status": "passed"} for row in report["missing"]])
        if not report["deferred_epochs"]:
            break
        assert len(recorded) < 6
    assert [(row["eval_id"], row["epoch"]) for row in recorded] == [
        ("concepts/agent-registries", 1), ("concepts/agent-registries", 2),
        ("concepts/agent-registries", 3), ("concepts/wei-per-ether", 1),
        ("concepts/wei-per-ether", 2), ("concepts/wei-per-ether", 3)]
    assert plan(evals, config, players, recorded, wall_seconds=2600).report["missing_epochs"] == 0


def test_plan_rejects_one_epoch_larger_than_empty_window():
    config = small_config()
    evaluation = load_eval(ROOT / "evals/concepts/agent-registries", config)
    players, _ = select_actors(config, modes=["vanilla"], planning=True)
    with pytest.raises(ValueError, match="Config error: a single epoch.*concepts/agent-registries"):
        plan([evaluation], config, players, [], wall_seconds=1900)


def test_run_executes_saved_plan(tmp_path):
    config = small_config()
    evaluation = load_eval(ROOT / "evals/concepts/agent-registries", config)
    success, rows = run([evaluation], config, tmp_path, answer="reference", wall_seconds=2150)
    report = json.loads((tmp_path / "plan.json").read_text())
    assert success
    assert [(row["epoch"], row["status"]) for row in rows] == [(1, "passed"), (2, "passed")]
    assert [row["epoch"] for row in report["missing"]] == [1, 2]
    assert [row["epoch"] for row in report["deferred"]] == [3]


def test_run_prepares_only_initially_admitted_evals(tmp_path, monkeypatch):
    import ethevals.runner as runner
    config = small_config()
    evaluation = load_eval(ROOT / "evals/concepts/agent-registries", config)
    deferred = load_eval(ROOT / "evals/concepts/wei-per-ether", config)
    original = runner.prepare_eval

    def prepare(evaluation, *args):
        if evaluation.id == deferred.id:
            raise RuntimeError("Deferred eval was prepared")
        return original(evaluation, *args)

    monkeypatch.setattr(runner, "prepare_eval", prepare)
    success, rows = run([evaluation, deferred], config, tmp_path, answer="reference", epochs=1, wall_seconds=2000)
    assert (success, [(row["eval_id"], row["status"]) for row in rows]) == (
        True, [("concepts/agent-registries", "passed")])


@pytest.mark.parametrize("folder, mode, seconds", [
    ("building/erc20-points-token", "internet", 3840),
    ("concepts/agent-registries", "vanilla", 3120),
])
def test_plan_includes_scoring_and_only_sandbox_container_time(folder, mode, seconds):
    config = small_config()
    config.time_limits = {"quiz": 1000, "build": 1000, "act": 1000}
    evaluation = load_eval(ROOT / "evals" / folder, config)
    players, _ = select_actors(config, modes=[mode], planning=True)
    report = plan([evaluation], config, players, [], epochs=1).report
    assert [(row["eval_id"], row["wall_seconds"]) for row in report["missing"]] == [(folder, seconds)]


def test_admitted_config_keys_keep_different_efforts_on_the_same_model(tmp_path, monkeypatch):
    config, evaluation = quiz()
    first = config.agents["opus"].model_copy(update={"model": "mockllm/shared", "harness": None})
    config.agents = {"high": first, "low": first.model_copy(update={"effort": "low"})}
    config.grader.model = "mockllm/grader"
    # Both providers are MockLLM. The gate key never reaches a provider request.
    monkeypatch.setenv("OPENROUTER_API_KEY", "inert-offline-gate-key")
    success, rows = run([evaluation], config, tmp_path, agents=["high", "low"], modes=["vanilla"], epochs=1, budget=20)
    assert success
    assert [(row["effort"], row["status"], row["attempt"]) for row in rows] == [
        ("high", "failed", 1), ("low", "failed", 1)]


@pytest.mark.parametrize("mode", ["vanilla", "internet"])
def test_planned_identity_matches_every_configured_provider(monkeypatch, mode):
    config, evaluation = quiz()
    monkeypatch.setenv("OPENROUTER_API_KEY", "inert-test-key")
    for key, settings in config.agents.items():
        planned, _ = select_actors(config, [key], [mode], planning=True)
        actual, _ = select_actors(config, [key], [mode])
        expected = (evaluation.id, evaluation.hash, settings.harness if mode == "internet" else None,
                    settings.model, settings.effort, mode, 1)
        for selection in (planned, actual):
            actor = selection(evaluation)[0][1]
            assert epoch_identity({"eval_id": evaluation.id, "eval_hash": evaluation.hash, "mode": mode,
                                   **actor.metadata}, 1) == expected


def test_late_publication_retains_current_source_and_newer_rows(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GH_TOKEN", "inert-test-token")
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
    ci.commit_results(ci.result_record(read_rows(rows)), "owner/repo", True)
    assert real_command("git", "show", f"{pushed[-1]}:source.txt", capture_output=True).stdout == "new source"
    assert ci.result_record() == newer
    # Retrying the same old observation after a newer publication preserves both rows.
    write_rows(rows, [old])
    ci.commit_results(ci.result_record(read_rows(rows)), "owner/repo", True)
    assert ci.result_record() == newer


def test_budget_stops_before_preparation(tmp_path, monkeypatch):
    config = small_config()
    evaluation = load_eval(ROOT / "evals/concepts/agent-registries", config)
    monkeypatch.setattr("ethevals.runner.prepare_eval", lambda *a: pytest.fail("Preparation ran"))
    with pytest.raises(ValueError, match="Budget exceeded"):
        run([evaluation], config, tmp_path, budget=1, epochs=1, modes=["vanilla"])
    report = json.loads((tmp_path / "plan.json").read_text())
    assert (report["worst_case_usd"], report["missing_epochs"], report["within_budget"]) == (4, 1, False)
