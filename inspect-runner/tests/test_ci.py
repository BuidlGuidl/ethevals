"""Committed results drive plans, fresh checkouts, and publication."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from ethevals.actors import select_actors
from ethevals.config import load_config
from ethevals.loader import load_eval
from ethevals.planning import plan
from ethevals.rows import fold_rows, read_rows, write_rows
from ethevals.runner import run

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("ci", ROOT / "scripts/ci.py")
ci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ci)


def cli(*args):
    environment = {key: value for key, value in os.environ.items() if key not in {
        "OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_AUTH_TOKEN", "EXA_API_KEY", "GH_TOKEN", "HF_TOKEN"}}
    return subprocess.run([sys.executable, *map(str, args)], cwd=ROOT, env=environment,
                          capture_output=True, text=True, timeout=60)


def test_fold_keeps_committed_rows_and_replaces_retried_identity(tmp_path):
    old = {"eval_id": "concepts/a", "eval_hash": "old", "model": "mockllm/model", "mode": "vanilla", "epoch": 1,
           "status": "passed", "attempt": 1}
    error = {**old, "eval_hash": "current", "status": "error"}
    retry = {**error, "status": "failed", "attempt": 2}
    new = {**old, "eval_id": "concepts/b"}
    path = tmp_path / "rows.jsonl"
    write_rows(path, fold_rows([old, error], [retry, new]))
    assert [(r["eval_id"], r["eval_hash"], r["status"], r["attempt"]) for r in read_rows(path)] == [
        ("concepts/a", "current", "failed", 2), ("concepts/a", "old", "passed", 1), ("concepts/b", "old", "passed", 1)]
    content, mtime = path.read_bytes(), path.stat().st_mtime_ns
    write_rows(path, fold_rows(read_rows(path), []))
    assert path.read_bytes() == content
    assert path.stat().st_mtime_ns == mtime


def test_plan_is_key_free_and_reserves_remaining_attempts(tmp_path):
    config = load_config()
    quiz = load_eval(ROOT / "evals/concepts/agent-registries", config)
    build = load_eval(ROOT / "evals/building/erc20-points-token", config)
    base = {"eval_id": quiz.id, "eval_hash": quiz.hash, "type": "quiz", "harness": None,
            "model": "openrouter/anthropic/claude-opus-5.5", "effort": "high", "mode": "vanilla", "answer_kind": None,
            "model_cost_usd": 0.25, "grader_cost_usd": 0.0}
    rows = [{**base, "epoch": 1, "status": "failed", "attempt": 1},
            {**base, "epoch": 2, "status": "error", "attempt": 1},
            {**base, "epoch": 3, "status": "error", "attempt": 2}]
    store = tmp_path / "rows.jsonl"
    write_rows(store, rows)
    # Discovery left no epoch row; the build remains missing without Docker or a key.
    (tmp_path / "discovery-errors.json").write_text(json.dumps([{"eval_id": build.id, "error": "Compiler failed"}]))
    result = cli("-m", "ethevals.cli", "plan", "--rows", store, "--evals", quiz.folder, build.folder,
                 "--models", "opus", "--modes", "vanilla", "internet", "--budget", "200")
    assert result.returncode == 1, result.stderr
    report = json.loads(result.stdout)
    assert report["missing_epochs"] == 7
    assert [(r["epoch"], r["attempt"], r["remaining_attempts"]) for r in report["missing"] if r["mode"] == "vanilla"] == [(2, 2, 1)]
    assert [(r["epoch"], r["attempt"]) for r in report["exhausted_errors"]] == [(3, 2)]
    assert report["worst_case_usd"] == 219.3728
    assert report["within_budget"] is False
    assert report["expected_usd_estimate"] is None
    assert report["history_covered_epochs"] == 1
    assert report["missing"][0]["expected_usd_estimate"] == 0.25
    players, _ = select_actors(config, ["opus"], ["vanilla"], planning=True)
    assert plan([quiz], config, players, rows).report["expected_usd_estimate"] == 0.25


def test_fresh_checkout_runs_only_missing_and_second_run_preserves_rows(tmp_path, monkeypatch):
    config = load_config()
    quiz = load_eval(ROOT / "evals/concepts/agent-registries", config)
    players, grade = select_actors(config, answer="reference")
    success, initial = run([quiz], config, tmp_path / "seed", answer="reference", epochs=1)
    assert success and initial[0]["status"] == "passed"
    rows = tmp_path / "committed/rows.jsonl"
    write_rows(rows, initial)
    output = tmp_path / "fresh"
    success, complete = run([quiz], config, output, answer="reference", rows_file=rows, epochs=3)
    assert success
    assert [r["epoch"] for r in complete] == [1, 2, 3]
    assert complete[0] == initial[0]
    assert len(list((output / "logs").glob("*.eval"))) == 2
    write_rows(rows, complete)
    saved = rows.read_bytes()

    def forbidden(*args, **kwargs):
        raise AssertionError("A completed store cannot run a model or discovery")

    monkeypatch.setattr("ethevals.runner.eval", forbidden)
    monkeypatch.setattr("ethevals.runner.prepare_eval", forbidden)
    success, repeated = run([quiz], config, tmp_path / "second", answer="reference", rows_file=rows, epochs=3)
    assert (success, repeated) == (True, complete)
    assert rows.read_bytes() == saved


@pytest.mark.parametrize("budget", ["0", "nan", "inf", "-1"])
def test_after_merge_gate_stops_before_a_model_or_secret(tmp_path, budget):
    output = tmp_path / "run"
    result = cli("scripts/ci.py", "after-merge", "--budget", budget, "--output", output,
                 "--rows", tmp_path / "rows.jsonl", "--evals", ROOT / "evals/concepts/agent-registries",
                 "--models", "opus", "--modes", "vanilla")
    assert result.returncode == 2
    assert "OPENROUTER_API_KEY is required" not in result.stderr
    assert not (output / "logs").exists()
    if budget == "0":
        report = json.loads((output / "plan.json").read_text())
        assert (report["missing_epochs"], report["worst_case_usd"], report["within_budget"]) == (3, 30, False)
        assert "No player or grader ran" in result.stderr
    else:
        assert "finite, nonnegative" in result.stderr


def test_after_merge_and_fold_commands_work_without_remote_writes(tmp_path):
    rows = tmp_path / "rows.jsonl"
    common = ["--rows", rows, "--evals", ROOT / "evals/concepts/agent-registries", "--modes", "vanilla"]
    first = cli("scripts/ci.py", "after-merge", "--output", tmp_path / "first", "--answer", "reference",
                "--epochs", "1", "--budget", "10", *common)
    assert first.returncode == 0, first.stdout + first.stderr
    (tmp_path / "first/paid-started.json").write_text(json.dumps({"run_id": "12-1", "commit": "a" * 40}))
    published = cli("scripts/ci.py", "publish-results", "--output", tmp_path / "first",
                    "--repo", "BuidlGuidl/ethevals")
    assert published.returncode == 0, published.stderr
    assert "Dry run: record 1 rows and 1 receipts" in published.stdout
    assert '"release": "results-12-1"' in published.stdout
    assert [(r["epoch"], r["status"]) for r in read_rows(tmp_path / "first/rows.jsonl")] == [(1, "passed")]
    assert not rows.exists()
    write_rows(rows, read_rows(tmp_path / "first/rows.jsonl"))
    second = cli("scripts/ci.py", "after-merge", "--output", tmp_path / "second", "--answer", "reference",
                 "--epochs", "3", "--budget", "20", *common)
    assert second.returncode == 0, second.stdout + second.stderr
    report = json.loads((tmp_path / "second/plan.json").read_text())
    assert [r["epoch"] for r in report["missing"]] == [2, 3]
    assert [r["status"] for r in read_rows(tmp_path / "second/rows.jsonl")] == ["passed"] * 3


def test_completed_paid_store_needs_neither_key_nor_budget(tmp_path):
    quiz = load_eval(ROOT / "evals/concepts/agent-registries", load_config())
    row = {"eval_id": quiz.id, "eval_hash": quiz.hash, "model": "openrouter/anthropic/claude-opus-5.5",
           "harness": None, "effort": "high", "mode": "vanilla", "answer_kind": None,
           "epoch": 1, "status": "failed", "attempt": 1}
    rows = tmp_path / "rows.jsonl"
    write_rows(rows, [row])
    before = rows.read_bytes(), rows.stat().st_mtime_ns
    result = cli("scripts/ci.py", "after-merge", "--output", tmp_path / "run", "--rows", rows,
                 "--evals", quiz.folder, "--models", "opus", "--modes", "vanilla", "--epochs", "1", "--budget", "0")
    assert result.returncode == 0, result.stderr
    report = json.loads((tmp_path / "run/plan.json").read_text())
    assert (report["missing_epochs"], report["worst_case_usd"], report["within_budget"]) == (0, 0, True)
    assert read_rows(tmp_path / "run/rows.jsonl") == [row]
    assert (rows.read_bytes(), rows.stat().st_mtime_ns) == before
    assert not (tmp_path / "run/logs").exists()


def test_publish_success_folds_links_and_errors_but_failure_keeps_committed_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(ci, "export_rows", lambda output: read_rows(output / "rows.jsonl"))
    monkeypatch.setattr(ci, "store_rows", lambda output: read_rows(output / "rows.jsonl"))
    config = load_config()
    quiz = load_eval(ROOT / "evals/concepts/agent-registries", config)
    previous = {"eval_id": quiz.id, "eval_hash": "stale", "model": "model", "mode": "vanilla", "epoch": 1,
                "status": "passed", "log_file": "results-old/old.eval"}
    new = {**previous, "eval_hash": quiz.hash, "log_file": "logs/new.eval"}
    error = {**new, "epoch": 2, "status": "error", "attempt": 2}
    output, rows = tmp_path / "run", tmp_path / "rows.jsonl"
    write_rows(rows, [previous])
    write_rows(output / "rows.jsonl", [new, error])
    (output / "logs").mkdir()
    (output / "logs/new.eval").write_bytes(b"fixture log")
    (output / "paid-started.json").write_text(json.dumps({"run_id": "1", "commit": "a" * 40}))
    records = []
    monkeypatch.setattr(ci, "stored_file", lambda ref, path: json.dumps(previous) + "\n" if str(path).endswith("rows.jsonl") else "{}")
    monkeypatch.setattr(ci, "commit_results", lambda rows, saved, *args: records.append((rows, saved)))
    args = argparse.Namespace(output=output, repo="owner/repo", publish=True)

    def fail(*args, **kwargs):
        raise subprocess.CalledProcessError(1, "gh")

    monkeypatch.setattr("ethevals.publish.subprocess.run", fail)
    assert ci.publish_artifacts(args) == 1
    assert [(r["status"], r.get("attempt")) for r in records[0][0]] == [("passed", None), ("error", 2), ("passed", None)]
    monkeypatch.setattr("ethevals.publish.subprocess.run", lambda *a, **kw: subprocess.CompletedProcess(a, 0))
    assert ci.publish_artifacts(args) == 0
    assert sorted((r["status"], r["log_file"]) for r in records[-1][0]) == [
        ("error", "logs/new.eval"), ("passed", "results-1/new.eval"), ("passed", "results-old/old.eval")]


def test_release_script_exports_without_upload(tmp_path):
    result = cli("scripts/ci.py", "release", "--output", tmp_path / "hf", "--hf-repo", "owner/dataset", "--license", "mit")
    assert result.returncode == 0, result.stderr
    assert '"dry_run": true' in result.stdout
    assert '"command": ["hf", "upload", "owner/dataset"' in result.stdout
    assert sorted(p.parent.name for p in (tmp_path / "hf/data").glob("*/test.jsonl")) == ["concepts-choice", "concepts-match-exact"]


def test_failed_discovery_stays_missing_without_using_attempts(tmp_path, monkeypatch):
    config = load_config()
    build = load_eval(ROOT / "evals/building/erc20-points-token", config)
    players, grade = select_actors(config, answer="reference")

    def failed(*args):
        raise RuntimeError("Reference compilation failed")

    monkeypatch.setattr("ethevals.runner.prepare_eval", failed)
    success, rows = run([build], config, tmp_path, answer="reference", epochs=1)
    assert (success, rows) == (False, [])
    assert json.loads((tmp_path / "discovery-errors.json").read_text())[0]["error"] == "Reference compilation failed"
    report = plan([build], config, players, read_rows(tmp_path / "rows.jsonl"), epochs=1).report
    assert [(r["eval_id"], r["attempt"], r["remaining_attempts"], r["worst_case_usd"]) for r in report["missing"]] == [
        ("building/erc20-points-token", 1, 2, 59.4576)]


def test_pending_results_branch_resumes_and_pr_appends_without_force(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GH_TOKEN", "inert-test-token")
    ci.command("git", "init", "-b", "main", capture_output=True)
    ci.command("git", "config", "user.name", "Test")
    ci.command("git", "config", "user.email", "test@example.org")
    rows = Path("results/rows.jsonl")
    first = {"eval_id": "concepts/a", "eval_hash": "a", "epoch": 1, "status": "passed"}
    second = {**first, "epoch": 2, "status": "error", "attempt": 1}
    write_rows(rows, [first])
    ci.command("git", "add", ".")
    ci.command("git", "commit", "-m", "Main results", capture_output=True)
    main = ci.command("git", "rev-parse", "HEAD", capture_output=True).stdout.strip()
    write_rows(rows, [first, second])
    ci.command("git", "add", ".")
    ci.command("git", "commit", "-m", "Pending results", capture_output=True)
    pending = ci.command("git", "rev-parse", "HEAD", capture_output=True).stdout.strip()
    ci.command("git", "update-ref", "refs/remotes/origin/ci/results", pending)
    ci.command("git", "checkout", "--detach", main, capture_output=True)
    ci.restore_results(rows)
    assert [(r["epoch"], r["status"], r.get("attempt")) for r in read_rows(rows)] == [(1, "passed", None), (2, "error", 1)]
    write_rows(rows, fold_rows(read_rows(rows), [{**second, "status": "failed", "attempt": 2}]))
    real_command, remote = ci.command, []

    def local_only(*args, **kwargs):
        if args[0] == "gh" or args[:2] == ("git", "push"):
            remote.append(list(args))
            return subprocess.CompletedProcess(args, 0, stdout="[]")
        return real_command(*args, **kwargs)

    monkeypatch.setattr(ci, "command", local_only)
    ci.commit_results(*ci.result_record(read_rows(rows)), "owner/repo", publish=True)
    assert remote[0][:3] == ["git", "push", "origin"]
    assert remote[0][3].endswith(":refs/heads/ci/results")
    commit = remote[0][3].split(":")[0]
    assert real_command("git", "show", "-s", "--format=%P", commit, capture_output=True).stdout.strip().split() == [main, pending]
    saved = real_command("git", "show", f"{commit}:results/rows.jsonl", capture_output=True).stdout
    assert [(r["epoch"], r["status"]) for r in map(json.loads, saved.splitlines())] == [(1, "passed"), (2, "failed")]
    assert remote[-1][:3] == ["gh", "pr", "create"]
    assert "--force" not in remote[0]


def test_all_artifact_receipts_precede_any_upload(tmp_path, monkeypatch):
    config = load_config()
    evaluation = load_eval(ROOT / "evals/concepts/agent-registries", config)
    first, second = tmp_path / "12-2", tmp_path / "12-10"
    run([evaluation], config, first, answer="reference", epochs=1)
    run([evaluation], config, second, answer="reference", epochs=2, rows_file=first / "rows.jsonl")
    for path in (first, second):
        (path / "paid-started.json").write_text(json.dumps({"run_id": path.name, "commit": "a" * 40}))
    stored = {"rows": [], "receipts": {}}
    def record(rows, receipts, *args):
        stored.update(rows=rows, receipts=receipts)
    monkeypatch.setattr(ci, "commit_results", record)
    monkeypatch.setattr(ci, "result_record", lambda rows=(), own_receipts=None: (
        ci.fold_rows(stored["rows"], rows), {**stored["receipts"], **(own_receipts or {})}))
    uploads = []
    def upload(output, repo, run_id, commit, **kwargs):
        assert sorted(stored["receipts"]) == ["12-10", "12-2"]
        assert [(r["epoch"], r["status"]) for r in stored["rows"]] == [(1, "passed"), (2, "passed")]
        uploads.append(run_id)
        if run_id == "12-2":
            raise RuntimeError("Old artifact upload failed")
        return {"rows_file": str(output / "rows.jsonl")}
    monkeypatch.setattr(ci, "publish_logs", upload)
    assert ci.publish_artifacts(argparse.Namespace(output=tmp_path, repo="owner/repo", publish=True)) == 1
    assert uploads == ["12-2", "12-10"]
    assert sorted(stored["receipts"]) == ["12-10", "12-2"]


def test_retry_opens_pr_after_successful_push(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GH_TOKEN", "offline-unused")
    ci.command("git", "init", "-b", "main", capture_output=True)
    ci.command("git", "config", "user.name", "Test")
    ci.command("git", "config", "user.email", "test@example.org")
    ci.command("git", "commit", "--allow-empty", "-m", "Initial", capture_output=True)
    ci.command("git", "update-ref", "refs/remotes/origin/main", "HEAD")
    command, pushes, prs = ci.command, [], []
    def remote(*args, **kwargs):
        if args[:2] == ("git", "push"):
            pushes.append(args[3])
            return subprocess.CompletedProcess(args, 0)
        if args[:3] == ("gh", "pr", "create"):
            prs.append(args)
            if len(prs) == 1:
                raise subprocess.CalledProcessError(1, "gh pr create")
            return subprocess.CompletedProcess(args, 0)
        if args[0] == "gh":
            return subprocess.CompletedProcess(args, 0, stdout="[]")
        return command(*args, **kwargs)
    monkeypatch.setattr(ci, "command", remote)
    row = {"eval_id": "test", "epoch": 1, "status": "error", "attempt": 1}
    with pytest.raises(subprocess.CalledProcessError):
        ci.commit_results([row], {"12-1": {"commit": "a" * 40}}, "owner/repo", True)
    ci.commit_results(*ci.result_record(), "owner/repo", True)
    assert len(pushes) == 1
    assert len(prs) == 2
    assert ci.result_record() == ([row], {"12-1": {"commit": "a" * 40}})


def test_missing_log_artifact_blocks_payment(monkeypatch):
    monkeypatch.setattr(ci, "result_record", lambda: ([], {}))
    def api(*args, **kwargs):
        assert args[-1] == "repos/owner/repo/actions/artifacts?per_page=100&page=1"
        return subprocess.CompletedProcess(args, 0, stdout=json.dumps({"artifacts": [
            {"name": "paid-12-1", "expired": False}]}))
    monkeypatch.setattr(ci, "command", api)
    with pytest.raises(ValueError, match="unrecorded paid attempts.*12-1"):
        ci.require_recorded_runs("owner/repo")


def test_plan_writes_paid_intent_without_a_provider(tmp_path, monkeypatch):
    config = load_config()
    evaluation = load_eval(ROOT / "evals/concepts/agent-registries", config)
    monkeypatch.setattr("ethevals.actors.model_actor", lambda *a: pytest.fail("Provider constructed"))
    monkeypatch.setenv("GITHUB_RUN_ID", "12")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "2")
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "step-output"))
    args = argparse.Namespace(output=tmp_path / "marker", rows=tmp_path / "rows.jsonl", restore_results=False,
                              models=["opus"], modes=["vanilla"], epochs=1, wall_seconds=16200, budget=10)
    assert ci.plan_paid(args, [evaluation], config) == 0
    source = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    assert json.loads((args.output / "paid-started.json").read_text()) == {"run_id": "12-2", "commit": source}
    assert (tmp_path / "step-output").read_text() == "ready=true\n"
    report = json.loads((args.output / "plan.json").read_text())
    assert (report["missing_epochs"], report["worst_case_usd"]) == (1, 10)


@pytest.mark.parametrize("identity", ["12", "12-two", "0-1", "12-0"])
def test_accept_loss_rejects_mistyped_identity(identity):
    result = cli("scripts/ci.py", "accept-loss", "--repo", "owner/repo", "--run-id", identity, "--reason", "Local proof")
    assert result.returncode == 2
    assert "RUN-ATTEMPT with positive integers" in result.stderr


def test_plan_paid_rejects_a_stalled_queue(tmp_path, monkeypatch, capsys):
    config = load_config()
    evaluation = load_eval(ROOT / "evals/concepts/agent-registries", config)
    players, _ = select_actors(config, ["opus"], ["vanilla"], planning=True)
    # A spent preparation window can defer even an epoch that fits a fresh job.
    stalled = plan([evaluation], config, players, [], epochs=1, wall_seconds=1100, preparation_seconds=100)
    assert (stalled.report["missing_epochs"], stalled.report["deferred_epochs"]) == (0, 1)
    monkeypatch.setattr(ci, "plan", lambda *a, **kw: stalled)
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "step-output"))
    output = tmp_path / "marker"
    monkeypatch.setattr(sys, "argv", ["ci.py", "plan-paid", "--output", str(output),
                                     "--models", "opus", "--modes", "vanilla", "--epochs", "1", "--budget", "10"])
    with pytest.raises(SystemExit) as error:
        ci.main()
    assert error.value.code == 2
    assert "ci: No epochs admitted; 1 remain deferred" in capsys.readouterr().err
    assert json.loads((output / "plan.json").read_text())["deferred_epochs"] == 1
    assert not (output / "paid-started.json").exists()
