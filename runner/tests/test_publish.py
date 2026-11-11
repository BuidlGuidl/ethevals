import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import time

import pytest

from ethevals.publish import publish_logs
from ethevals.trial_rows import results_row
from ethevals.secret_check import check_output


class ReleaseGitHub:
    """Keep a release across calls and fail after a chosen number of uploads."""

    def __init__(self, *, fail_after=None, failures=0, error=None):
        self.exists = False
        self.files = {}
        self.unfinished = set()
        self.sent = []
        self.batches = []
        self.waits = []
        self.fail_after = fail_after
        self.failures = failures
        self.error = error or "HTTP 403: You have exceeded a secondary rate limit"

    def __call__(self, command, **kwargs):
        operation = command[2] if command[1] == "release" else "assets"
        if operation == "view":
            result = subprocess.CompletedProcess(command, 0 if self.exists else 1,
                                                 stdout=json.dumps({"databaseId": 123}),
                                                 stderr="" if self.exists else "release not found")
            if kwargs.get("check"):
                result.check_returncode()
            return result
        if operation == "assets":
            assert "--paginate" in command and "--slurp" in command
            files = [{"name": name, "size": size, "state": "open" if name in self.unfinished else "uploaded"}
                     for name, size in self.files.items()]
            pages = [files[i:i + 100] for i in range(0, len(files), 100)]
            return subprocess.CompletedProcess(command, 0, stdout=json.dumps(pages))
        assert operation in {"create", "upload"}
        if operation == "create":
            assert not self.exists
            self.exists = True
        else:
            assert self.exists
        paths = [Path(arg) for arg in command if arg.startswith("/") and Path(arg).is_file()]
        if paths:
            self.batches.append([path.name for path in paths])
        try:
            for path in paths:
                if self.fail_after is not None and len(self.sent) >= self.fail_after and self.failures:
                    self.failures -= 1
                    raise subprocess.CalledProcessError(1, command, stderr=self.error)
                if path.name in self.files:
                    assert "--clobber" in command
                self.files[path.name] = path.stat().st_size
                self.unfinished.discard(path.name)
                self.sent.append(path.name)
        except subprocess.CalledProcessError:
            if operation == "create":
                self.exists = False
                self.files.clear()
            raise
        return subprocess.CompletedProcess(command, 0, stdout="")


@pytest.fixture
def release_github(monkeypatch):
    github = ReleaseGitHub()
    monkeypatch.setattr("ethevals.publish.subprocess.run", github)
    monkeypatch.setattr(time, "sleep", github.waits.append)
    return github


def many_rows(tmp_path, count=40):
    row = recorded_row(tmp_path)
    return [{**row, "trial": trial} for trial in range(1, count + 1)]


def assert_uploaded(report, github):
    assert github.files == {asset["name"]: Path(asset["source"]).stat().st_size for asset in report["assets"]}
    receipt = [json.loads(line) for line in Path(report["rows_file"]).read_text().splitlines()]
    assert receipt == report["rows"]


def test_rate_limit_failure_keeps_uploaded_files(tmp_path, release_github):
    rows = many_rows(tmp_path)
    release_github.fail_after = 15
    release_github.failures = 100
    with pytest.raises((RuntimeError, subprocess.CalledProcessError)):
        publish_logs(tmp_path / "release", "owner/repo", "12", "a" * 40, publish=True, rows=rows)
    assert release_github.exists
    assert set(release_github.files) == set(release_github.sent)
    assert len(release_github.files) == 15
    assert not (tmp_path / "release/published").exists()


def test_continue_sends_only_missing_files_and_writes_receipt(tmp_path, release_github):
    rows = many_rows(tmp_path, 60)
    release_github.fail_after = 105
    release_github.failures = 100
    with pytest.raises((RuntimeError, subprocess.CalledProcessError)):
        publish_logs(tmp_path / "release", "owner/repo", "12", "a" * 40, publish=True, rows=rows)
    completed = set(release_github.files)
    release_github.sent.clear()
    release_github.failures = 0
    report = publish_logs(tmp_path / "release", "owner/repo", "12", "a" * 40, publish=True, rows=rows)
    assert len(completed) == 105
    assert set(release_github.sent) == {asset["name"] for asset in report["assets"]} - completed
    assert_uploaded(report, release_github)


def test_rate_limit_inside_batch_waits_and_continues(tmp_path, release_github):
    release_github.fail_after = 15
    release_github.failures = 2
    report = publish_logs(tmp_path / "release", "owner/repo", "12", "a" * 40,
                          publish=True, rows=many_rows(tmp_path))
    assert len(release_github.sent) == len(set(release_github.sent)) == 80
    assert [wait for wait in release_github.waits if wait >= 60] == [60, 120]
    assert_uploaded(report, release_github)


def test_continue_replaces_cut_off_file(tmp_path, release_github):
    rows = many_rows(tmp_path)
    staged = publish_logs(tmp_path / "release", "owner/repo", "12", "a" * 40, rows=rows)
    release_github.exists = True
    release_github.files = {asset["name"]: Path(asset["source"]).stat().st_size for asset in staged["assets"]}
    broken = staged["assets"][0]["name"]
    release_github.files[broken] = 1
    report = publish_logs(tmp_path / "release", "owner/repo", "12", "a" * 40, publish=True, rows=rows)
    assert release_github.sent == [broken]
    assert_uploaded(report, release_github)


def test_continue_sends_again_a_file_github_never_finished(tmp_path, release_github):
    rows = many_rows(tmp_path)
    staged = publish_logs(tmp_path / "release", "owner/repo", "12", "a" * 40, rows=rows)
    release_github.exists = True
    release_github.files = {asset["name"]: Path(asset["source"]).stat().st_size for asset in staged["assets"]}
    unfinished = staged["assets"][0]["name"]
    release_github.unfinished = {unfinished}
    report = publish_logs(tmp_path / "release", "owner/repo", "12", "a" * 40, publish=True, rows=rows)
    assert release_github.sent == [unfinished]
    assert_uploaded(report, release_github)


def test_batch_pace_stays_under_eighty_files_per_minute(tmp_path, release_github):
    report = publish_logs(tmp_path / "release", "owner/repo", "12", "a" * 40,
                          publish=True, rows=many_rows(tmp_path, 500))
    assert len(release_github.sent) == 1000
    assert max(map(len, release_github.batches)) <= 10
    assert 1000 * 60 / sum(release_github.waits) < 80
    assert_uploaded(report, release_github)


def test_rate_limit_gives_up_with_progress_and_no_receipt(tmp_path, release_github):
    release_github.fail_after = 15
    release_github.failures = 100
    with pytest.raises(RuntimeError, match="15 files up, 65 left.*[Rr]erun.*failed job.*continue"):
        publish_logs(tmp_path / "release", "owner/repo", "12", "a" * 40,
                     publish=True, rows=many_rows(tmp_path))
    assert release_github.failures == 93
    assert [wait for wait in release_github.waits if wait >= 60] == [60, 120, 240, 480, 960, 1920]
    assert len(release_github.files) == 15
    assert not (tmp_path / "release/published").exists()


def recorded_row(tmp_path):
    fixture = Path(__file__).parent / "fixtures/harbor/recorded-trial"
    folder = tmp_path / "jobs/job/trial"
    shutil.copytree(fixture, folder)
    metadata = json.loads((fixture / "board.json").read_text())
    (folder.parent / "board.json").write_text(json.dumps(metadata))
    check_output(tmp_path, {})
    return results_row(folder, metadata)


def test_release_stages_trajectory_and_all_verifier_output_without_remote_writes(tmp_path):
    row = recorded_row(tmp_path)
    details = Path(row["verifier_files"]) / "reward-details.json"
    check_output(tmp_path, {})
    report = publish_logs(tmp_path / "release", "owner/repo", "12", "a" * 40, rows=[row])
    assert (report["dry_run"], report["release"]) == (True, "results-12")
    assert len(report["assets"]) == 2
    trajectory, verifier = report["assets"]
    assert Path(trajectory["source"]).read_bytes() == Path(row["trajectory_file"]).read_bytes()
    with tarfile.open(verifier["source"]) as archive:
        assert json.load(archive.extractfile("reward.json")) == row["rewards"]
        assert archive.extractfile("reward-details.json").read() == details.read_bytes()
    assert report["rows"][0]["trajectory_url"] == trajectory["url"]
    assert report["rows"][0]["verifier_url"] == verifier["url"]
    assert not (tmp_path / "release/published").exists()


def test_release_failure_writes_no_receipt_and_retry_uploads_same_assets(tmp_path, release_github):
    row = recorded_row(tmp_path)
    output = tmp_path / "release"
    release_github.fail_after = 0
    release_github.failures = 1
    release_github.error = "HTTP 403: Resource not accessible by integration"
    with pytest.raises(subprocess.CalledProcessError):
        publish_logs(output, "owner/repo", "12", "a" * 40, publish=True, rows=[row])
    assert release_github.exists
    assert release_github.waits == []
    assert not (output / "published").exists()
    report = publish_logs(output, "owner/repo", "12", "a" * 40, publish=True, rows=[row])
    assert release_github.sent == [asset["name"] for asset in report["assets"]]
    assert_uploaded(report, release_github)
    receipt = json.loads(Path(report["rows_file"]).read_text())
    assert receipt["trajectory_url"] == report["rows"][0]["trajectory_url"]
    already = publish_logs(output, "owner/repo", "13", "a" * 40, rows=[receipt])
    assert (already["assets"], already["rows"]) == ([], [receipt])


@pytest.mark.parametrize("kind", ["trajectory", "verifier"])
def test_release_rejects_missing_files(tmp_path, kind):
    row = recorded_row(tmp_path)
    if kind == "trajectory":
        Path(row["trajectory_file"]).unlink()
    else:
        shutil.rmtree(row["verifier_files"])
    with pytest.raises(ValueError, match="publication check"):
        publish_logs(tmp_path / "release", "owner/repo", "12", "a" * 40, rows=[row])


def test_release_rejects_verifier_symlinks(tmp_path):
    row = recorded_row(tmp_path)
    secret = tmp_path / "secret"
    secret.write_text("private")
    (Path(row["verifier_files"]) / "outside").symlink_to(secret)
    with pytest.raises(ValueError, match="publication check"):
        publish_logs(tmp_path / "release", "owner/repo", "12", "a" * 40, rows=[row])


def test_release_keeps_output_for_a_trial_with_a_verification_error(tmp_path):
    row = recorded_row(tmp_path)
    folder = Path(row["verifier_files"]).parent
    (folder / "verifier/reward-details.json").unlink()
    metadata = json.loads((folder / "board.json").read_text())
    row = results_row(folder, metadata)
    check_output(tmp_path, {})
    assert (row["status"], row["error_kind"]) == ("error", "verification")
    report = publish_logs(tmp_path / "release", "owner/repo", "12", "a" * 40, rows=[row])
    assert len(report["assets"]) == 2
    assert report["rows"][0]["status"] == "error"
    assert report["rows"][0]["trajectory_url"].startswith("https://")
