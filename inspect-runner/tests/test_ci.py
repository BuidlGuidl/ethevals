from pathlib import Path
import importlib.util
import json
import shutil
import subprocess
import sys

import pytest

from ethevals.trial_rows import fold_rows, read_rows, write_rows
from test_publish import recorded_row


ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("ci", ROOT / "scripts/ci.py")
ci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ci)


def test_pr_checks_run_harbor_without_the_removed_public_tasks(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(ci, "command", lambda *args, **kwargs: calls.append((args, kwargs)))
    monkeypatch.setattr(sys, "argv", ["ci.py", "checks", "--output", str(tmp_path)])
    assert ci.main() == 0
    assert calls == [
        ((sys.executable, "-m", "ethevals.cli", "free-check", "--output", tmp_path / "harbor"), {}),
        ((sys.executable, "-m", "pytest", "-q"), {}),
        ((sys.executable, "-m", "pytest", "-q", "--run-docker", "-m", "docker",
          "--ignore=inspect-runner/tests/test_agents_docker.py"), {}),
        *((('pnpm', task), {"cwd": "site"}) for task in ("test", "typecheck", "lint", "build")),
    ]


def test_pending_results_branch_resumes_and_pr_appends_without_force(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GH_TOKEN", "inert-test-token")
    ci.command("git", "init", "-b", "main", capture_output=True)
    ci.command("git", "config", "user.name", "Test")
    ci.command("git", "config", "user.email", "test@example.org")
    rows = Path("results/rows.jsonl")
    first = {"schema_version": 7, "task_id": "concepts/a", "task_hash": "a", "trial": 1, "status": "passed", "attempt": 1}
    second = {**first, "trial": 2, "status": "error", "attempt": 1}
    Path("source.txt").write_text("old source")
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
    planned = main
    Path("source.txt").write_text("current source")
    ci.command("git", "add", "source.txt")
    ci.command("git", "commit", "-m", "Update source", capture_output=True)
    main = ci.command("git", "rev-parse", "HEAD", capture_output=True).stdout.strip()
    ci.command("git", "update-ref", "refs/remotes/origin/main", main)
    ci.command("git", "checkout", "--detach", planned, capture_output=True)
    ci.restore_results(rows)
    assert [(r["trial"], r["status"], r.get("attempt")) for r in read_rows(rows)] == [(1, "passed", 1), (2, "error", 1)]
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
    assert [(r["trial"], r["status"]) for r in map(json.loads, saved.splitlines())] == [(1, "passed"), (2, "failed")]
    assert real_command("git", "show", f"{commit}:source.txt", capture_output=True).stdout == "current source"
    assert remote[-1][:3] == ["gh", "pr", "create"]
    assert "--force" not in remote[0]


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
    row = {"schema_version": 7, "task_id": "test", "trial": 1, "status": "error", "attempt": 1}
    with pytest.raises(subprocess.CalledProcessError):
        ci.commit_results([row], "owner/repo", True)
    ci.commit_results(ci.result_record(), "owner/repo", True)
    assert len(pushes) == 1
    assert len(prs) == 2
    assert ci.result_record() == [row]


def test_publish_records_downloaded_trials_before_upload_and_retries_release(tmp_path, monkeypatch):
    row = recorded_row(tmp_path)
    fixture = Path(row["trajectory_file"]).parent.parent
    artifact = tmp_path / "trial-run-12-1-0/jobs/job"
    artifact.mkdir(parents=True)
    shutil.copyfile(fixture / "board.json", artifact / "board.json")
    shutil.copytree(fixture, artifact / "trial")
    # The earlier artifact is superseded by attempt 2, even if download order differs.
    later = tmp_path / "trial-run-12-2-0/jobs/job"
    shutil.copytree(artifact, later)
    metadata = json.loads((later / "board.json").read_text())
    metadata["attempt"] = 2
    (later / "board.json").write_text(json.dumps(metadata))
    saved = []
    real_command = ci.command

    def remote(*args, **kwargs):
        if args[:2] == ("git", "push"):
            commit = args[3].split(":")[0]
            content = real_command("git", "show", f"{commit}:results/rows.jsonl", capture_output=True).stdout
            saved.append([json.loads(line) for line in content.splitlines()])
            return subprocess.CompletedProcess(args, 0)
        if args[0] == "gh":
            return subprocess.CompletedProcess(args, 0, stdout="[]")
        return real_command(*args, **kwargs)

    repository = tmp_path / "repo"
    repository.mkdir()
    monkeypatch.chdir(repository)
    monkeypatch.setenv("GH_TOKEN", "offline-unused")
    ci.command("git", "init", "-b", "main", capture_output=True)
    ci.command("git", "config", "user.name", "Test")
    ci.command("git", "config", "user.email", "test@example.org")
    ci.command("git", "commit", "--allow-empty", "-m", "Initial", capture_output=True)
    ci.command("git", "update-ref", "refs/remotes/origin/main", "HEAD")
    monkeypatch.setattr(ci, "command", remote)
    real_run = subprocess.run
    uploads = []

    def upload(args, **kwargs):
        if args[0] != "gh":
            return real_run(args, **kwargs)
        assert [(r["trial"], r["attempt"], r["status"]) for r in saved[-1]] == [(1, 2, "passed")]
        assert saved[-1][0]["trajectory_url"].startswith("https://github.com/owner/repo/releases/download/results-12/")
        if args[2] == "view":
            return subprocess.CompletedProcess(args, 0)
        uploads.append(args)
        if len(uploads) == 1:
            raise subprocess.CalledProcessError(1, args)
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr("ethevals.publish.subprocess.run", upload)
    import argparse
    args = argparse.Namespace(output=tmp_path, repo="owner/repo", run_id="12", commit="b" * 40, publish=True)
    assert ci.publish_artifacts(args) == 1
    assert len(saved) == 1
    assert ci.result_record()[0]["attempt"] == 2
    assert ci.publish_artifacts(args) == 0
    assert len(saved) == 1
    assert uploads[0] == uploads[1]
    assert uploads[1][:7] == ["gh", "release", "upload", "results-12", "--repo", "owner/repo", "--clobber"]
    assert json.loads((tmp_path / "combined/release.json").read_text())["dry_run"] is False
