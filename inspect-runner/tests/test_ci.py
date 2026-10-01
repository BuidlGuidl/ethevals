from pathlib import Path
import argparse
import importlib.util
import json
import shutil
import subprocess
import sys

from ethevals.actors import select_actors
from ethevals.loader import load_eval
from ethevals.planning import plan
from ethevals.rows import fold_rows, previous_rows, read_rows, write_rows
from inspect_ai.log import read_eval_log, write_eval_log
import pytest

from support import catalog_quiz, cli, fixture_config, run


ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("ci", ROOT / "scripts/ci.py")
ci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ci)


@pytest.mark.parametrize("operation", ["resume", "publish"])
def test_truncated_log_keeps_completed_epoch(tmp_path, monkeypatch, caplog, operation):
    monkeypatch.delenv("PYTEST_CURRENT_TEST")
    config, evaluation = catalog_quiz()
    output = tmp_path / "eval-run-12-1"
    run([evaluation], config, output, answer="reference", epochs=1)
    complete = next((output / "logs").glob("*.eval"))
    (output / "logs/unfinished.eval").write_bytes(complete.read_bytes()[:100])
    if operation == "resume":
        actors_for, _ = select_actors(config, answer="reference", planning=True)
        report = plan([evaluation], config, actors_for, previous_rows(output), epochs=1).report
        assert report["missing_epochs"] == 0
        report = plan([evaluation], config, actors_for, previous_rows(output), epochs=2).report
        assert [row["epoch"] for row in report["missing"]] == [2]
    else:
        recorded = []
        monkeypatch.setattr(ci, "commit_results", lambda rows, *args: recorded.extend(rows))
        monkeypatch.setattr(ci, "publish_logs", lambda *args, **kwargs: {"rows_file": str(output / "rows.jsonl")})
        assert ci.publish_artifacts(argparse.Namespace(output=tmp_path, repo="owner/repo", publish=True, run_id="12", commit="b" * 40)) == 0
        assert any((r["eval_hash"], r["epoch"], r["status"]) == (evaluation.hash, 1, "passed") for r in recorded)
    assert any(record.levelname == "WARNING" and str(output / "logs/unfinished.eval") in record.message
               for record in caplog.records)


def test_timeout_artifact_rebuilds_attempts_and_failed_publication_keeps_record(tmp_path, monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST")
    monkeypatch.setattr(ci, "result_record", lambda rows=(): list(rows))
    config, evaluation = catalog_quiz()
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
    args = argparse.Namespace(output=tmp_path, repo="owner/repo", publish=True, run_id="12", commit="b" * 40)
    assert ci.publish_artifacts(args) == 1
    assert sorted((r["status"], r["attempt"]) for r in persisted[0]) == [("error", 2), ("passed", 1)]
    agents_for, _ = select_actors(config, answer="reference", planning=True)
    report = plan([evaluation], config, agents_for, persisted[0], epochs=2).report
    assert (report["missing_epochs"], len(report["exhausted_errors"])) == (0, 1)


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
            assert args[args.index("--base") + 1] == "main"
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


def test_fresh_checkout_runs_only_missing_and_second_run_preserves_rows(tmp_path, monkeypatch):
    config = fixture_config()
    quiz = load_eval(ROOT / "evals/concepts/agent-registries", config)
    agents_for, grade = select_actors(config, answer="reference")
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
        raise AssertionError("A completed store cannot run a model or prepare containers")

    monkeypatch.setattr("ethevals.runner.eval", forbidden)
    monkeypatch.setattr("ethevals.runner.prepare_compose", forbidden)
    success, repeated = run([quiz], config, tmp_path / "second", answer="reference", rows_file=rows, epochs=3)
    assert (success, repeated) == (True, complete)
    assert rows.read_bytes() == saved


@pytest.mark.parametrize("budget", ["0", "nan"])
def test_plan_epochs_gate_stops_before_a_model_or_secret(tmp_path, budget):
    from support import small_config
    config_path = tmp_path / "config.yaml"
    config_path.write_text(small_config().model_dump_json())
    output = tmp_path / "eval-run-1"
    result = cli("scripts/ci.py", "plan-epochs", "--budget", budget, "--output", output,
                 "--config", config_path,
                 "--rows", tmp_path / "rows.jsonl", "--evals", ROOT / "evals/concepts/agent-registries",
                 "--models", "test", "--modes", "vanilla")
    assert result.returncode == (1 if budget == "0" else 2)
    assert not (output / "logs").exists()
    if budget == "0":
        report = json.loads((output / "plan.json").read_text())
        assert (report["missing_epochs"], report["within_budget"]) == (3, False)
        assert json.loads(result.stdout)["within_budget"] is False
    else:
        assert "finite, nonnegative" in result.stderr
    published = cli("scripts/ci.py", "publish-results", "--output", tmp_path, "--repo", "owner/repo", "--run-id", "12", "--commit", "b" * 40)
    assert (published.returncode, published.stdout) == (0, ""), published.stderr


def test_completed_paid_store_needs_neither_key_nor_budget(tmp_path):
    from support import small_config
    config = small_config()
    config_path = tmp_path / "config.yaml"
    config_path.write_text(config.model_dump_json())
    quiz = load_eval(ROOT / "evals/concepts/agent-registries", config)
    row = {"eval_id": quiz.id, "eval_hash": quiz.hash, "model": "mockllm/test",
           "harness": None, "effort": "high", "mode": "vanilla",
           "epoch": 1, "status": "error", "attempt": 2}
    rows = tmp_path / "rows.jsonl"
    write_rows(rows, [row])
    before = rows.read_bytes(), rows.stat().st_mtime_ns
    output = tmp_path / "eval-run-1"
    result = cli("scripts/ci.py", "plan-epochs", "--output", output, "--rows", rows, "--config", config_path,
                 "--evals", quiz.folder, "--models", "test", "--modes", "vanilla", "--epochs", "1", "--budget", "0")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["missing_epochs"] == 0
    report = json.loads((output / "plan.json").read_text())
    assert (report["missing_epochs"], report["worst_case_usd"], report["within_budget"]) == (0, 0, True)
    assert report["exhausted_errors"] == [row]
    assert read_rows(output / "rows.jsonl") == [row]
    assert (rows.read_bytes(), rows.stat().st_mtime_ns) == before
    assert not (output / "logs").exists()
    published = cli("scripts/ci.py", "publish-results", "--output", tmp_path, "--repo", "owner/repo", "--run-id", "12", "--commit", "b" * 40)
    assert (published.returncode, published.stdout) == (0, ""), published.stderr


def test_plan_epochs_restores_completed_epochs_without_eval(tmp_path, monkeypatch):
    from support import small_config
    monkeypatch.chdir(tmp_path)
    config = small_config()
    config_path = tmp_path / "config.json"
    config_path.write_text(config.model_dump_json())
    quiz = load_eval(ROOT / "evals/concepts/agent-registries", config)
    rows = [{"eval_id": quiz.id, "eval_hash": quiz.hash, "model": "mockllm/test",
             "harness": None, "effort": "high", "mode": "vanilla", "epoch": epoch,
             "status": "passed", "attempt": 1} for epoch in (1, 2)]
    ci.command("git", "init", "-b", "main", capture_output=True)
    ci.command("git", "config", "user.name", "Test")
    ci.command("git", "config", "user.email", "test@example.org")
    ci.command("git", "commit", "--allow-empty", "-m", "Source", capture_output=True)
    ci.command("git", "update-ref", "refs/remotes/origin/main", "HEAD")
    write_rows(Path("results/rows.jsonl"), rows)
    ci.command("git", "add", "results/rows.jsonl")
    ci.command("git", "commit", "-m", "Completed epochs", capture_output=True)
    ci.command("git", "update-ref", "refs/remotes/origin/ci/results", "HEAD")
    ci.command("git", "checkout", "--detach", "origin/main", capture_output=True)
    monkeypatch.setattr("ethevals.runner.eval", lambda *args, **kwargs: pytest.fail("Completed epochs called eval"))
    output = tmp_path / "eval-run-1"
    monkeypatch.setattr(sys, "argv", ["ci.py", "plan-epochs", "--restore-results", "--output", str(output),
        "--config", str(config_path), "--evals", str(quiz.folder), "--models", "test",
        "--modes", "vanilla", "--epochs", "2", "--budget", "0"])
    assert ci.main() == 0
    assert json.loads((output / "plan.json").read_text())["missing_epochs"] == 0
    assert read_rows(output / "rows.jsonl") == rows


def test_plan_emits_two_evals(tmp_path):
    from support import small_config
    config_path = tmp_path / "config.json"
    config_path.write_text(small_config().model_dump_json())
    output, github_output = tmp_path / "plan", tmp_path / "github-output"
    args = argparse.Namespace(output=output, restore_results=False, github_output=github_output)
    assert ci.plan_epochs(args, ["--config", str(config_path), "--rows", str(tmp_path / "rows.jsonl"),
                                "--evals", "evals/concepts/agent-registries", "evals/transactions/send-six-decimal-token",
                                "--agents", "test-agent", "--modes", "internet", "--epochs", "1", "--budget", "100"]) == 0
    values = dict(line.split("=", 1) for line in github_output.read_text().splitlines())
    matrix = json.loads(values["matrix"])
    assert values["missing_epochs"] == "2"
    assert [(row["eval_id"], row["actor_key"], row["mode"], row["epoch"])
            for row in matrix["include"]] == [
        ("concepts/agent-registries", "test-agent", "internet", 1),
        ("transactions/send-six-decimal-token", "test-agent", "internet", 1)]


def test_plan_defers_epochs_above_256_and_next_run_picks_them_up(tmp_path):
    from support import small_config
    config = small_config()
    config_path = tmp_path / "config.json"
    config_path.write_text(config.model_dump_json())
    previous, github_output = tmp_path / "rows.jsonl", tmp_path / "github-output"
    options = ["--config", str(config_path), "--rows", str(previous), "--evals", "evals/concepts/agent-registries",
               "--models", "test", "--modes", "vanilla", "--epochs", "257", "--budget", "1028"]
    assert ci.plan_epochs(argparse.Namespace(output=tmp_path / "first", restore_results=False,
                                            github_output=github_output), options) == 0
    matrix = json.loads(github_output.read_text().splitlines()[0].removeprefix("matrix="))
    assert [row["epoch"] for row in matrix["include"]] == list(range(1, 257))
    quiz = load_eval(ROOT / "evals/concepts/agent-registries", config)
    write_rows(previous, [{"eval_id": quiz.id, "eval_hash": quiz.hash, "model": "mockllm/test", "harness": None,
                          "effort": "high", "mode": "vanilla", "epoch": epoch, "status": "passed", "attempt": 1}
                         for epoch in range(1, 257)])
    assert ci.plan_epochs(argparse.Namespace(output=tmp_path / "second", restore_results=False,
                                            github_output=github_output), options) == 0
    matrix = json.loads(github_output.read_text().splitlines()[-2].removeprefix("matrix="))
    assert [row["epoch"] for row in matrix["include"]] == [257]


def test_matrix_runs_one_saved_plan_row_with_its_attempt(tmp_path):
    from support import small_config
    config = small_config()
    config_path = tmp_path / "config.json"
    config_path.write_text(config.model_dump_json())
    quiz = load_eval(ROOT / "evals/concepts/agent-registries", config)
    row = {"eval_id": quiz.id, "eval_hash": quiz.hash, "model": "mockllm/test", "harness": None,
           "effort": "high", "mode": "vanilla", "epoch": 2, "status": "error", "attempt": 1}
    previous = tmp_path / "previous.jsonl"
    write_rows(previous, [row])
    plan_dir = tmp_path / "plan"
    assert ci.plan_epochs(argparse.Namespace(output=plan_dir, restore_results=False, github_output=None),
                          ["--config", str(config_path), "--rows", str(previous), "--evals", str(quiz.folder),
                           "--models", "test", "--modes", "vanilla", "--epochs", "3", "--budget", "10"]) == 0
    output = tmp_path / "epoch"
    assert ci.ethevals(["run", "--config", str(plan_dir / "config.json"), "--rows", str(plan_dir / "rows.jsonl"),
                       "--output", str(output), "--evals", str(quiz.folder), "--models", "test", "--modes", "vanilla",
                       "--epoch", "2", "--budget", "2"]) == 0
    assert [(item["epoch"], item["attempt"], item["status"], item["effort"])
            for item in read_rows(output / "rows.jsonl")] == [(2, 2, "failed", "high")]
    assert len(list((output / "logs").glob("*.eval"))) == 1
    assert read_rows(plan_dir / "rows.jsonl") == [row]


def test_publish_success_folds_links_and_errors_but_failure_keeps_committed_rows(tmp_path, monkeypatch):
    from support import small_config
    config = small_config()
    quiz = load_eval(ROOT / "evals/concepts/agent-registries", config)
    previous = {"eval_id": quiz.id, "eval_hash": "stale", "model": "model", "mode": "vanilla", "epoch": 1,
                "status": "passed", "log_file": "results-old/old.eval"}
    new = {**previous, "eval_hash": quiz.hash, "log_file": "logs/new.eval"}
    error = {**new, "epoch": 2, "status": "error", "attempt": 2}
    output, rows = tmp_path / "eval-run-1", tmp_path / "rows.jsonl"
    write_rows(rows, [previous])
    write_rows(output / "rows.jsonl", [new, error])
    (output / "logs").mkdir()
    (output / "logs/new.eval").write_text("Log asset")
    monkeypatch.setattr(ci, "store_rows", lambda output: read_rows(output / "rows.jsonl"))
    records = []
    monkeypatch.setattr(ci, "stored_file", lambda ref, path: json.dumps(previous) + "\n" if str(path).endswith("rows.jsonl") else "{}")
    monkeypatch.setattr(ci, "commit_results", lambda rows, *args: records.append(rows))
    args = argparse.Namespace(output=tmp_path, repo="owner/repo", publish=True, run_id="12", commit="b" * 40)

    real_subprocess = subprocess.run
    def fail(command, **kwargs):
        if command[0] == "git":
            return real_subprocess(command, **kwargs)
        raise subprocess.CalledProcessError(1, "gh")

    monkeypatch.setattr("ethevals.publish.subprocess.run", fail)
    assert ci.publish_artifacts(args) == 1
    assert [(r["status"], r.get("attempt")) for r in records[0]] == [("passed", None), ("error", 2), ("passed", None)]
    assert records[0][0]["log_url"] == "https://github.com/owner/repo/releases/download/results-12/new.eval"
    commands = []
    def upload(command, **kwargs):
        if command[0] == "git":
            return real_subprocess(command, **kwargs)
        commands.append(command)
        return subprocess.CompletedProcess(command, 1 if command[2] == "view" else 0)
    monkeypatch.setattr("ethevals.publish.subprocess.run", upload)
    assert ci.publish_artifacts(args) == 0
    assert sorted((r["status"], r["log_file"]) for r in records[-1]) == [
        ("error", "logs/new.eval"), ("passed", "logs/new.eval"), ("passed", "results-old/old.eval")]
    assert [(r["status"], r.get("log_url")) for r in records[-1]] == [
        ("passed", "https://github.com/owner/repo/releases/download/results-12/new.eval"), ("error", None), ("passed", None)]
    assert commands[-1][:8] == ["gh", "release", "create", "results-12", "--repo", "owner/repo", "--target", "b" * 40]


def test_failed_preparation_stays_missing_without_using_attempts(tmp_path, monkeypatch):
    config = fixture_config()
    build = load_eval(ROOT / "inspect-runner/tests/fixtures/building/erc20-points-token", config)
    agents_for, grade = select_actors(config, answer="reference")

    def failed(*args):
        raise RuntimeError("Docker build failed")

    monkeypatch.setattr("ethevals.runner.prepare_compose", failed)
    success, rows = run([build], config, tmp_path, answer="reference", epochs=1)
    assert (success, rows) == (False, [])
    assert json.loads((tmp_path / "preparation-errors.json").read_text())[0]["error"] == "Docker build failed"
    report = plan([build], config, agents_for, read_rows(tmp_path / "rows.jsonl"), epochs=1).report
    assert [(r["eval_id"], r["attempt"], r["remaining_attempts"]) for r in report["missing"]] == [
        ("building/erc20-points-token", 1, 2)]


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
    ci.command("git", "update-ref", "refs/remotes/origin/main", main)
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
    ci.commit_results(ci.result_record(read_rows(rows)), "owner/repo", publish=False)
    assert remote == []
    ci.commit_results(ci.result_record(read_rows(rows)), "owner/repo", publish=True)
    assert remote[0][:3] == ["git", "push", "origin"]
    assert remote[0][3].endswith(":refs/heads/ci/results")
    commit = remote[0][3].split(":")[0]
    assert real_command("git", "show", "-s", "--format=%P", commit, capture_output=True).stdout.strip().split() == [main, pending]
    saved = real_command("git", "show", f"{commit}:results/rows.jsonl", capture_output=True).stdout
    assert [(r["epoch"], r["status"]) for r in map(json.loads, saved.splitlines())] == [(1, "passed"), (2, "failed")]
    assert remote[-1][:3] == ["gh", "pr", "create"]
    assert "--force" not in remote[0]


def test_all_artifact_rows_precede_any_upload_and_retry_uses_the_same_release(tmp_path, monkeypatch):
    config, evaluation = catalog_quiz()
    first, second = tmp_path / "eval-run-12-1-0", tmp_path / "eval-run-12-1-1"
    run([evaluation], config, first, answer="reference", epoch=1, modes=["vanilla"])
    run([evaluation], config, second, answer="reference", epoch=2, modes=["vanilla"])
    stored, releases = [], []
    monkeypatch.setattr(ci, "result_record", lambda rows=(): list(rows))
    monkeypatch.setattr(ci, "commit_results", lambda rows, *args: stored.append(rows))
    real_subprocess = subprocess.run

    def upload(command, **kwargs):
        if command[0] != "gh":
            return real_subprocess(command, **kwargs)
        assert [(row["epoch"], row["status"], row["log_url"].split("/")[-2]) for row in stored[-1]] == [
            (1, "passed", "results-12"), (2, "passed", "results-12")]
        if command[2] == "view":
            return subprocess.CompletedProcess(command, 0 if releases else 1)
        releases.append(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("ethevals.publish.subprocess.run", upload)
    args = argparse.Namespace(output=tmp_path, repo="owner/repo", publish=True, run_id="12", commit="b" * 40)
    assert ci.publish_artifacts(args) == 0
    assert len(releases) == len(stored) == 1
    assert releases[0][:8] == ["gh", "release", "create", "results-12", "--repo", "owner/repo", "--target", "b" * 40]
    assert len([value for value in releases[0] if value.endswith(".eval")]) == 2
    assert [(row["epoch"], row["status"], row["log_url"].split("/")[-2]) for row in stored[0]] == [
        (1, "passed", "results-12"), (2, "passed", "results-12")]

    retry = tmp_path / "retry"
    for artifact in (first, second):
        shutil.copytree(artifact, retry / artifact.name)
    args.output = retry
    assert ci.publish_artifacts(args) == 0
    assert releases[1][:7] == ["gh", "release", "upload", "results-12", "--repo", "owner/repo", "--clobber"]
    assert len(releases) == len(stored) == 2
    assert stored[1] == stored[0]


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
        ci.commit_results([row], "owner/repo", True)
    ci.commit_results(ci.result_record(), "owner/repo", True)
    assert len(pushes) == 1
    assert len(prs) == 2
    assert ci.result_record() == [row]
