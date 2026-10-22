import json
from pathlib import Path
import shutil
import subprocess
import tarfile

import pytest

from ethevals.publish import publish_logs
from ethevals.trial_rows import results_row


def recorded_row(tmp_path):
    fixture = Path(__file__).parent / "fixtures/harbor/recorded-trial"
    folder = tmp_path / "trial"
    shutil.copytree(fixture, folder)
    metadata = json.loads((fixture / "board.json").read_text())
    return results_row(folder, metadata)


def test_release_stages_trajectory_and_all_verifier_output_without_remote_writes(tmp_path):
    row = recorded_row(tmp_path)
    judge = Path(row["verifier_files"]) / "judge.json"
    judge.write_text('{"checks":{"explained":{"passed":true,"reason":"Names the unit."}}}')
    report = publish_logs(tmp_path / "release", "owner/repo", "12", "a" * 40, rows=[row])
    assert (report["dry_run"], report["release"]) == (True, "results-12")
    assert len(report["assets"]) == 2
    trajectory, verifier = report["assets"]
    assert Path(trajectory["source"]).read_bytes() == Path(row["trajectory_file"]).read_bytes()
    with tarfile.open(verifier["source"]) as archive:
        assert json.load(archive.extractfile("reward.json")) == row["rewards"]
        assert "reward-details.json" in archive.getnames()
        assert archive.extractfile("judge.json").read() == judge.read_bytes()
    assert report["rows"][0]["trajectory_url"] == trajectory["url"]
    assert report["rows"][0]["verifier_url"] == verifier["url"]
    assert not (tmp_path / "release/published").exists()


def test_release_failure_writes_no_receipt_and_retry_uploads_same_assets(tmp_path, monkeypatch):
    row = recorded_row(tmp_path)
    output = tmp_path / "release"
    commands = []

    def failed(command, **kwargs):
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr("ethevals.publish.subprocess.run", failed)
    with pytest.raises(subprocess.CalledProcessError):
        publish_logs(output, "owner/repo", "12", "a" * 40, publish=True, rows=[row])
    assert not (output / "published").exists()

    def success(command, **kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("ethevals.publish.subprocess.run", success)
    report = publish_logs(output, "owner/repo", "12", "a" * 40, publish=True, rows=[row], resume=True)
    assert commands[-1][:7] == ["gh", "release", "upload", "results-12", "--repo", "owner/repo", "--clobber"]
    assert commands[-1][7:] == [asset["source"] for asset in report["assets"]]
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
    with pytest.raises(ValueError, match="Missing"):
        publish_logs(tmp_path / "release", "owner/repo", "12", "a" * 40, rows=[row])


def test_release_rejects_verifier_symlinks(tmp_path):
    row = recorded_row(tmp_path)
    secret = tmp_path / "secret"
    secret.write_text("private")
    (Path(row["verifier_files"]) / "outside").symlink_to(secret)
    with pytest.raises(ValueError, match="must stay inside"):
        publish_logs(tmp_path / "release", "owner/repo", "12", "a" * 40, rows=[row])


def test_release_keeps_output_for_a_trial_with_a_verification_error(tmp_path):
    row = recorded_row(tmp_path)
    folder = Path(row["verifier_files"]).parent
    (folder / "verifier/reward-details.json").unlink()
    metadata = json.loads((folder / "board.json").read_text())
    row = results_row(folder, metadata)
    assert (row["status"], row["error_kind"]) == ("error", "verification")
    report = publish_logs(tmp_path / "release", "owner/repo", "12", "a" * 40, rows=[row])
    assert len(report["assets"]) == 2
    assert report["rows"][0]["status"] == "error"
    assert report["rows"][0]["trajectory_url"].startswith("https://")
