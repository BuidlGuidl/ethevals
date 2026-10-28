import json
from pathlib import Path
import shutil
import subprocess
import tarfile

import pytest

from ethevals.publish import publish_logs
from ethevals.trial_rows import results_row
from ethevals.secret_check import check_output


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


def preverification_error(tmp_path, *, trajectory=False, hub_url=None):
    row = recorded_row(tmp_path)
    folder = Path(row["verifier_files"]).parent
    shutil.rmtree(folder / "verifier")
    if not trajectory:
        shutil.rmtree(folder / "agent")
    result = json.loads((folder / "result.json").read_text())
    result.update(agent_setup=None, agent_execution=None, agent_result=None,
                  verifier=None, verifier_result=None, exception_info={
                      "exception_type": "EnvironmentStartTimeoutError",
                      "exception_message": "Environment start timed out after 600.0 seconds",
                      "exception_traceback": "EnvironmentStartTimeoutError",
                      "occurred_at": result["finished_at"],
                  })
    (folder / "result.json").write_text(json.dumps(result))
    metadata = json.loads((folder / "board.json").read_text())
    metadata["trial"] = 2
    (folder / "board.json").write_text(json.dumps(metadata))
    (folder.parent / "board.json").write_text(json.dumps(metadata))
    check_output(tmp_path, {})
    return results_row(folder, metadata, trajectory_url=hub_url)


@pytest.mark.parametrize("hub_url", [None, "https://hub.harborframework.com/jobs/job/trials/trial"])
def test_release_keeps_a_checked_error_when_verification_never_started(tmp_path, hub_url):
    row = preverification_error(tmp_path, hub_url=hub_url)
    report = publish_logs(tmp_path / "release", "owner/repo", "12", "a" * 40, rows=[row])
    assert report["rows"] == [row]
    assert (row["status"], row["error_kind"], row["rewards"], row["checks"]) == (
        "error", "EnvironmentStartTimeoutError", {}, {})
    assert row["trajectory_url"] == hub_url
    assert report["assets"] == []
    assert report["command"] == []
    assert not list((tmp_path / "release").rglob("*.tar.gz"))
    assert not Path(row["verifier_files"]).exists()
    assert not report["rows"][0].get("verifier_url")


def test_release_stages_available_output_in_a_batch_with_a_preverification_error(tmp_path):
    failed = preverification_error(tmp_path / "error", trajectory=True)
    completed = recorded_row(tmp_path / "completed")
    report = publish_logs(tmp_path / "release", "owner/repo", "12", "a" * 40, rows=[failed, completed])
    error_row, completed_row = report["rows"]
    assert {key: value for key, value in error_row.items() if key not in {"trajectory_file", "trajectory_url"}} == {
        key: value for key, value in failed.items() if key not in {"trajectory_file", "trajectory_url"}}
    assert (completed_row["status"], completed_row["rewards"], completed_row["checks"]) == (
        "passed", completed["rewards"], completed["checks"])
    assert len(report["assets"]) == 3
    assert [asset["url"] for asset in report["assets"]] == sorted([
        error_row["trajectory_url"], completed_row["trajectory_url"], completed_row["verifier_url"]])
    for source, linked in [(failed, error_row), (completed, completed_row)]:
        assert Path(linked["trajectory_file"]).read_bytes() == Path(source["trajectory_file"]).read_bytes()
    verifier = next(asset for asset in report["assets"] if asset["url"] == completed_row["verifier_url"])
    with tarfile.open(verifier["source"]) as archive:
        assert {member.name: archive.extractfile(member).read() for member in archive.getmembers()} == {
            path.relative_to(completed["verifier_files"]).as_posix(): path.read_bytes()
            for path in Path(completed["verifier_files"]).rglob("*") if path.is_file()}


@pytest.mark.parametrize("evidence", [
    "completed", "unfinished", "passed_row", "verifier_started", "verifier_result", "step_verifier", "step_result"])
def test_release_rejects_missing_verifier_output_without_a_saved_preverification_failure(tmp_path, evidence):
    row = preverification_error(tmp_path)
    folder = Path(row["verifier_files"]).parent
    result = json.loads((folder / "result.json").read_text())
    if evidence == "completed":
        result["exception_info"] = None
    elif evidence == "unfinished":
        result["finished_at"] = None
    elif evidence == "passed_row":
        row["status"] = "passed"
    elif evidence == "verifier_started":
        result["verifier"] = {"started_at": result["finished_at"]}
    elif evidence == "verifier_result":
        result["verifier_result"] = {"rewards": {"reward": 1}}
    elif evidence == "step_verifier":
        result["step_results"] = [{"step_name": "first", "verifier": {"started_at": result["finished_at"]}}]
    else:
        result["step_results"] = [{"step_name": "first", "verifier_result": {"rewards": {"reward": 1}}}]
    (folder / "result.json").write_text(json.dumps(result))
    check_output(tmp_path, {})
    with pytest.raises(ValueError, match="Missing verifier output"):
        publish_logs(tmp_path / "release", "owner/repo", "12", "a" * 40, rows=[row])


def test_release_rejects_changes_to_a_checked_preverification_failure(tmp_path):
    row = preverification_error(tmp_path)
    folder = Path(row["verifier_files"]).parent
    (folder / "result.json").write_text("{}")
    with pytest.raises(ValueError, match="publication check"):
        publish_logs(tmp_path / "release", "owner/repo", "12", "a" * 40, rows=[row])
