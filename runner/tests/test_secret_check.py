import asyncio
import argparse
import json
from pathlib import Path
import shutil

import pytest
from harbor.job import Job

from ethevals.job_config import FileCredential, load_job
from ethevals.jobs import budget_check, plan, run
from ethevals.publish import publish_logs
from ethevals.secret_check import check_folder, check_output, remember_secrets, require_checked, secret_values, stage_artifact
from ethevals.trial_rows import recover_rows
from test_jobs import job_config, task_folder


@pytest.mark.parametrize("location", ["agent/trajectory.json", "verifier/reward-details.json"])
def test_local_run_withholds_secret_files_and_keeps_a_safe_error_row(tmp_path, monkeypatch, capsys, location):
    config_path = job_config(tmp_path, "free")
    data = json.loads(config_path.read_text())
    data["agents"]["added-agent"] = {**data["agents"].pop("local"), "name": "oracle",
                                    "required_env": ["NEW_AGENT_CREDENTIAL"]}
    config_path.write_text(json.dumps(data))
    config = load_job(config_path)
    monkeypatch.setenv("NEW_AGENT_CREDENTIAL", "offline-new-agent-credential")
    task = task_folder(tmp_path)

    async def saved_result(job):
        folder = job.job_dir / "trial"
        shutil.copytree(Path(__file__).parent / "fixtures/harbor/recorded-trial", folder)
        (folder / location).write_text("offline-new-agent-credential")

    monkeypatch.setattr(Job, "run", saved_result)
    output = tmp_path / "out"
    report = budget_check(plan([task], config, [], n_attempts=1), 0)
    assert asyncio.run(run(report, config, output, [])) is False
    row = json.loads((output / "rows.jsonl").read_text())
    assert (row["status"], row["error_kind"], row["trajectory_file"], row["verifier_files"]) == (
        "error", "secret", None, None)
    assert "NEW_AGENT_CREDENTIAL" in row["error_reason"]
    assert "offline-new-agent-credential" not in json.dumps(row)
    assert "offline-new-agent-credential" not in capsys.readouterr().err
    release = publish_logs(output / "release", "owner/repo", "22", "a" * 40, rows=[row])
    assert (release["assets"], release["rows"][0]["status"]) == ([], "error")


@pytest.mark.parametrize("location", [None, "agent/trajectory.json", "result.json"])
def test_ci_failure_still_exports_only_checked_files_with_tokens_available(tmp_path, monkeypatch, capsys, caplog, location):
    import yaml
    from test_ci import ci

    config = load_job(job_config(tmp_path, "free"))
    config.agents["local"].name = "oracle"
    task = task_folder(tmp_path)
    saved = tmp_path / "plan"
    saved.mkdir()
    (saved / "config.json").write_text(config.model_dump_json())
    item = plan([task], config, [], n_attempts=1)["missing"][0]
    (saved / "trials.json").write_text(json.dumps([{
        "missing": [item], "selected": [], "worst_case_usd": 0}]))
    monkeypatch.setenv("CODEX_AUTH_JSON", json.dumps({"tokens": {"access_token": "offline-ci-access-token"}}))
    monkeypatch.setenv("GITHUB_ACTIONS", "true")

    async def interrupted(job):
        folder = job.job_dir / "trial"
        shutil.copytree(Path(__file__).parent / "fixtures/harbor/recorded-trial", folder)
        if location:
            (folder / location).write_text('{"id":"offline-ci-access-token"}')
        raise RuntimeError("The trial step stopped")

    monkeypatch.setattr(Job, "run", interrupted)
    workflow = yaml.safe_load((Path(ci.__file__).parents[1] / ".github/workflows/results.yml").read_text())
    uploads = [step for step in workflow["jobs"]["matrix"]["steps"]
               if step.get("uses", "").startswith("actions/upload-artifact@")]
    assert len(uploads) == 1
    output = tmp_path / "results/ci-run"
    artifact = tmp_path / uploads[0]["with"]["path"]
    with pytest.raises(RuntimeError, match="trial step stopped"):
        ci.run_trial(argparse.Namespace(plan=saved, index=0, output=output))
    rows = recover_rows(artifact)
    assert rows[0]["status"] == ("error" if location else "passed")
    release = publish_logs(tmp_path / "release", "owner/repo", "22", "a" * 40, rows=rows)
    assert len(release["assets"]) == (0 if location else 2)
    assert all(b"offline-ci-access-token" not in file.read_bytes()
               for file in artifact.rglob("*") if file.is_file())
    messages = capsys.readouterr().err
    assert "offline-ci-access-token" not in messages
    assert "offline-ci-access-token" not in caplog.text
    if location:
        assert "::warning::Trial withheld: secret found for CODEX_AUTH_JSON.tokens.access_token" in messages


@pytest.mark.parametrize("source,label,value", [
    ("host", "ARCHIVE_RPC_URL", "https://archive.example/offline-provider-key"),
    ("auth", "CODEX_AUTH_JSON.tokens.refresh_token", "offline-refresh-token-value"),
    ("auth_override", "CODEX_AUTH_JSON.tokens.refresh_token", "offline-overridden-token-value"),
    ("judge", "CUSTOM_JUDGE_KEY", "offline-judge-key-value"),
    ("literal", "AGENT_ACCESS_TOKEN", "offline-literal-token-value"),
])
def test_whole_job_check_withholds_artifact_and_release_for_declared_secrets(tmp_path, monkeypatch, source, label, value):
    config = load_job(job_config(tmp_path, "free"))
    task = task_folder(tmp_path)
    if source == "host":
        (task / "environment/docker-compose.yaml").write_text(
            "services:\n  browser:\n    environment:\n      URL: ${ARCHIVE_RPC_URL:?Set ARCHIVE_RPC_URL}\n")
        monkeypatch.setenv(label, value)
    elif source.startswith("auth"):
        auth = tmp_path / "auth.json"
        auth.write_text(json.dumps({"auth_mode": "chatgpt", "tokens": {"refresh_token": value}}))
        config.agents["local"].required_files = [FileCredential(path=str(auth), policy="plan_tokens")]
        if source == "auth_override":
            other = tmp_path / "host-auth.json"
            other.write_text('{"tokens":{"access_token":"offline-unused-host-token"}}')
            monkeypatch.setenv("AUTH_PATH", str(other))
            config.agents["local"].env["AUTH_PATH"] = str(auth)
            config.agents["local"].required_files[0].path = "${AUTH_PATH}"
        # Load through the real config parser, including its file credential declaration.
        config = type(config).model_validate_json(config.model_dump_json())
    elif source == "literal":
        config.agents["local"].env[label] = value
    else:
        config.judge.key_env = label
        monkeypatch.setenv(label, value)
    raw = tmp_path / "raw"
    folder = raw / "jobs/job/trial"
    shutil.copytree(Path(__file__).parent / "fixtures/harbor/recorded-trial", folder)
    shutil.copyfile(folder / "board.json", folder.parent / "board.json")
    (folder / "artifacts").mkdir()
    (folder / "artifacts/output.bin").write_bytes(b"\x00" + value.encode() + b"\xff")
    check_output(raw, secret_values(config, [task]))
    artifact = tmp_path / "artifact"
    stage_artifact(raw, artifact)
    rows = recover_rows(artifact)
    assert (rows[0]["status"], rows[0]["error_kind"], rows[0]["trajectory_url"]) == ("error", "secret", None)
    assert label in rows[0]["error_reason"]
    assert all(value.encode() not in path.read_bytes() for path in artifact.rglob("*") if path.is_file())
    assert sorted(path.relative_to(artifact).as_posix() for path in artifact.rglob("*") if path.is_file()) == [
        "jobs/job/publication-check.json", "rows.jsonl"]
    release = publish_logs(tmp_path / "release", "owner/repo", "22", "a" * 40, rows=rows)
    assert (release["assets"], release["rows"][0]["error_kind"]) == ([], "secret")


def test_a_checked_job_still_publishes_after_the_artifact_upload_drops_its_empty_folders(tmp_path):
    config = load_job(job_config(tmp_path, "free"))
    raw, artifact = tmp_path / "raw", tmp_path / "artifact"
    folder = raw / "jobs/job/trial"
    shutil.copytree(Path(__file__).parent / "fixtures/harbor/recorded-trial", folder)
    shutil.copyfile(folder / "board.json", folder.parent / "board.json")
    # Harbor leaves empty folders in a trial, and GitHub's artifact upload keeps only files.
    (folder / "artifacts/logs/artifacts").mkdir(parents=True)
    (folder / "artifacts/logs/.hidden").write_text("kept with include-hidden-files\n")
    check_output(raw, secret_values(config, []))
    stage_artifact(raw, artifact)
    for path in sorted(artifact.rglob("*"), reverse=True):
        if path.is_dir() and not any(path.iterdir()):
            path.rmdir()
    require_checked(artifact / "jobs/job")
    report = publish_logs(tmp_path / "release", "owner/repo", "22", "a" * 40, rows=recover_rows(artifact))
    assert report["rows"][0]["status"] == "passed"


def test_clean_checked_artifact_survives_download_and_force_flags(tmp_path):
    config = load_job(job_config(tmp_path, "free"))
    config.agents["local"].env = {"NEW_FORCE_AUTH": "1", "AGENT_BASE_URL": "https://models.example/v1"}
    raw, artifact = tmp_path / "raw", tmp_path / "artifact"
    folder = raw / "jobs/job/trial"
    shutil.copytree(Path(__file__).parent / "fixtures/harbor/recorded-trial", folder)
    shutil.copyfile(folder / "board.json", folder.parent / "board.json")
    (folder / "artifacts").mkdir()
    (folder / "artifacts/settings.txt").write_text("https://models.example/v1")
    check_output(raw, secret_values(config, []))
    stage_artifact(raw, artifact)
    shutil.rmtree(raw)
    report = publish_logs(tmp_path / "release", "owner/repo", "22", "a" * 40, rows=recover_rows(artifact))
    assert (len(report["assets"]), report["rows"][0]["status"]) == (2, "passed")
    assert report["rows"][0]["trajectory_url"].startswith("https://github.com/owner/repo/releases/")


def test_unchecked_and_changed_jobs_cannot_stage_release_files(tmp_path):
    raw = tmp_path / "raw"
    folder = raw / "jobs/job/trial"
    shutil.copytree(Path(__file__).parent / "fixtures/harbor/recorded-trial", folder)
    shutil.copyfile(folder / "board.json", folder.parent / "board.json")
    rows = recover_rows(raw)
    with pytest.raises(ValueError, match="publication check"):
        publish_logs(tmp_path / "release", "owner/repo", "22", "a" * 40, rows=rows)
    check_output(raw, {})
    (folder.parent / "job.log").write_text("changed since the check")
    with pytest.raises(ValueError, match="publication check"):
        stage_artifact(raw, tmp_path / "artifact")
    check_output(raw, {})
    require_checked(folder.parent)
    report = publish_logs(tmp_path / "release", "owner/repo", "22", "a" * 40, rows=rows)
    assert len(report["assets"]) == 2


def test_a_check_killed_while_writing_its_receipt_leaves_the_job_readable(tmp_path, monkeypatch):
    raw = tmp_path / "raw"
    folder = raw / "jobs/job/trial"
    shutil.copytree(Path(__file__).parent / "fixtures/harbor/recorded-trial", folder)
    shutil.copyfile(folder / "board.json", folder.parent / "board.json")
    check_output(raw, {})
    write_text = Path.write_text

    def killed(path, text, *args, **kwargs):
        # Opening the file empties it, then the kill lands before any text.
        write_text(path, "", *args, **kwargs)
        raise KeyboardInterrupt

    monkeypatch.setattr(Path, "write_text", killed)
    with pytest.raises(KeyboardInterrupt):
        check_output(raw, {})
    monkeypatch.undo()
    check_output(raw, {})
    require_checked(folder.parent)
    assert len(recover_rows(raw)) == 1


def test_release_cannot_substitute_an_unchecked_trajectory(tmp_path):
    raw = tmp_path / "raw"
    folder = raw / "jobs/job/trial"
    shutil.copytree(Path(__file__).parent / "fixtures/harbor/recorded-trial", folder)
    shutil.copyfile(folder / "board.json", folder.parent / "board.json")
    check_output(raw, {})
    rows = recover_rows(raw)
    outside = tmp_path / "unchecked.json"
    outside.write_text("offline-credential-outside-the-job")
    rows[0]["trajectory_file"] = str(outside)
    with pytest.raises(ValueError, match="checked job"):
        publish_logs(tmp_path / "release", "owner/repo", "22", "a" * 40, rows=rows)


def test_failed_copy_leaves_no_unchecked_files_in_the_artifact_path(tmp_path, monkeypatch):
    raw, artifact = tmp_path / "raw", tmp_path / "artifact"
    folder = raw / "jobs/job/trial"
    shutil.copytree(Path(__file__).parent / "fixtures/harbor/recorded-trial", folder)
    shutil.copyfile(folder / "board.json", folder.parent / "board.json")
    check_output(raw, {})
    copytree = shutil.copytree

    def changed_copy(source, destination, *args, **kwargs):
        result = copytree(source, destination, *args, **kwargs)
        if Path(source) == folder.parent:
            (Path(destination) / "trial/agent/trajectory.json").write_text("offline-copy-race-token")
        return result

    monkeypatch.setattr(shutil, "copytree", changed_copy)
    with pytest.raises(ValueError, match="publication check"):
        stage_artifact(raw, artifact)
    assert not artifact.exists()


def test_planning_without_credentials_cannot_approve_an_interrupted_job(tmp_path, capsys):
    from ethevals.cli import main

    raw = tmp_path / "raw"
    folder = raw / "jobs/job/trial"
    shutil.copytree(Path(__file__).parent / "fixtures/harbor/recorded-trial", folder)
    shutil.copyfile(folder / "board.json", folder.parent / "board.json")
    config_path, task = job_config(tmp_path, "free"), task_folder(tmp_path)
    assert main(["plan", "--config", str(config_path), "--tasks", str(task),
                 "--output", str(raw), "--rows", str(tmp_path / "none")]) == 0
    assert json.loads(capsys.readouterr().out)["missing_trials"] == 2
    with pytest.raises(ValueError, match="publication check"):
        publish_logs(tmp_path / "release", "owner/repo", "22", "a" * 40, rows=recover_rows(raw))


@pytest.mark.parametrize("current", [b"offline-original-token", b"offline-replacement-token"])
def test_interrupted_trial_cannot_publish_after_its_credential_changes(tmp_path, current):
    raw = tmp_path / "raw"
    job = raw / "jobs/job"
    job.mkdir(parents=True)
    remember_secrets(job, {"OFFLINE_TOKEN": {b"offline-original-token"}})
    folder = job / "trial"
    shutil.copytree(Path(__file__).parent / "fixtures/harbor/recorded-trial", folder)
    shutil.copyfile(folder / "board.json", job / "board.json")
    (folder / "agent/trajectory.json").write_text("offline-original-token")
    check_output(raw, {"OFFLINE_TOKEN": {current}}, require_inventory=True)
    artifact = tmp_path / "artifact"
    stage_artifact(raw, artifact)
    rows = recover_rows(artifact)
    assert (rows[0]["status"], rows[0]["trajectory_file"]) == ("error", None)
    assert "OFFLINE_TOKEN" in rows[0]["error_reason"]
    assert all(b"offline-original-token" not in file.read_bytes() and b"offline-replacement-token" not in file.read_bytes()
               for file in artifact.rglob("*") if file.is_file())
    release = publish_logs(tmp_path / "release", "owner/repo", "22", "a" * 40, rows=rows)
    assert (release["assets"], release["rows"][0]["status"]) == ([], "error")


def test_check_reads_binary_chunk_boundaries_and_names_without_following_links(tmp_path):
    folder = tmp_path / "job"
    folder.mkdir()
    value = b"offline-binary-token"
    (folder / "output.bin").write_bytes(b"\x00" * (1024 * 1024 - 3) + value + b"\xff")
    (folder / "offline-filename-token").write_text("clean")
    (folder / "publication-check.json").write_text("offline-receipt-token")
    names, digest = check_folder(folder, {"BINARY_TOKEN": {value}, "NAME_TOKEN": {b"offline-filename-token"},
                                        "RECEIPT_TOKEN": {b"offline-receipt-token"}})
    assert names == ["BINARY_TOKEN", "NAME_TOKEN", "RECEIPT_TOKEN"]
    assert len(digest) == 64
    (folder / "link").symlink_to(tmp_path / "private")
    with pytest.raises(ValueError, match="symlinks"):
        check_folder(folder, {})


@pytest.mark.docker
def test_real_harbor_trial_withholds_an_environment_secret_from_both_publish_paths(tmp_path, monkeypatch):
    fixture = Path(__file__).parent / "fixtures/harbor"
    monkeypatch.syspath_prepend(str(fixture.resolve()))
    monkeypatch.setenv("OFFLINE_AGENT_TOKEN", "offline-real-trial-token")
    config = load_job(job_config(tmp_path, "free"))
    config.agents["local"].name = "local_agent:LeakingAgent"
    config.agents["local"].required_env = ["OFFLINE_AGENT_TOKEN"]
    task = fixture / "concepts/question"
    report = budget_check(plan([task], config, [], n_attempts=1), 0)
    raw, artifact = tmp_path / "raw", tmp_path / "artifact"
    assert asyncio.run(run(report, config, raw, [])) is False
    trajectory = next((raw / "jobs").glob("*/*/agent/trajectory.json"))
    assert b"offline-real-trial-token" in trajectory.read_bytes()
    stage_artifact(raw, artifact)
    rows = recover_rows(artifact)
    release = publish_logs(tmp_path / "release", "owner/repo", "22", "a" * 40, rows=rows)
    assert (rows[0]["status"], rows[0]["error_kind"], release["assets"]) == ("error", "secret", [])
    assert "OFFLINE_AGENT_TOKEN" in rows[0]["error_reason"]
    assert all(b"offline-real-trial-token" not in file.read_bytes()
               for file in artifact.rglob("*") if file.is_file())
