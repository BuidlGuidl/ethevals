import json
from pathlib import Path
import shutil
import subprocess

import pytest

from ethevals.cli import main
from ethevals.job_config import load_job
from ethevals.jobs import plan
from ethevals.publish import publish_logs
from ethevals.secret_check import check_output
from ethevals.trial_rows import fold_rows, read_rows, recover_rows
from test_jobs import job_config, task_folder


JOB_ID = "ceba51dd-02c4-4eb5-9139-1ad7220a4a13"
TRIAL_ID = "80ff2732-b7e9-4d92-8f37-ae29eb2cb10d"
HUB_URL = f"https://hub.harborframework.com/jobs/{JOB_ID}/trials/{TRIAL_ID}"


def saved_job(tmp_path):
    config = load_job(job_config(tmp_path, "api_key"))
    config.hub = load_job().hub
    output = tmp_path / "out"
    task = task_folder(tmp_path)
    item = plan([task], config, [], n_attempts=1)["missing"][0]
    folder = output / "jobs/local-name"
    fixture = Path(__file__).parent / "fixtures/harbor/recorded-trial"
    shutil.copytree(fixture, folder / "trial")
    # Keep the paid identity from the plan and the recorded agent's version.
    item["agent_version"] = json.loads((fixture / "board.json").read_text())["agent_version"]
    (folder / "board.json").write_text(json.dumps(item))
    (folder / "result.json").write_text(json.dumps({"id": JOB_ID}))
    (folder / "config.json").write_text("{}")
    check_output(output, {})
    return output, task, config


def test_upload_uses_harbor_ids_and_release_keeps_its_copy(tmp_path, monkeypatch):
    from ethevals.hub import upload_hub

    output, _, config = saved_job(tmp_path)
    monkeypatch.setenv("HARBOR_API_KEY", "offline-hub-key")
    commands = []

    def uploaded(command, **kwargs):
        commands.append((command, kwargs["env"]["HARBOR_API_KEY"]))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("ethevals.hub.subprocess.run", uploaded)
    upload_hub(output, config)
    assert [(command[:2], Path(command[2]).name, command[3:], key) for command, key in commands] == [
        (["harbor", "upload"], "local-name", ["--org", "buidlguidl", "--public"], "offline-hub-key")]
    # Receipt and rows survive artifact download to another path.
    downloaded = tmp_path / "download"
    shutil.copytree(output, downloaded)
    shutil.rmtree(output)
    rows = recover_rows(downloaded)
    assert (rows[0]["trajectory_url"], rows[0]["status"]) == (HUB_URL, "passed")
    fallback = {**rows[0], "trajectory_url": "https://github.com/owner/repo/releases/download/results-23/trajectory.json"}
    assert fold_rows([fallback], rows)[0]["trajectory_url"] == HUB_URL
    release = publish_logs(tmp_path / "release", "owner/repo", "23", "a" * 40, rows=rows)
    assert release["rows"][0]["trajectory_url"] == HUB_URL
    assert [asset["name"].split("-")[0] for asset in release["assets"]] == ["trajectory", "verifier"]
    trajectory = Path(release["assets"][0]["source"])
    assert json.loads(trajectory.read_text())["steps"][-1]["message"] == "metre"


@pytest.mark.parametrize("failure", ["missing-key", "upload-error", "timeout", "unchecked", "withheld", "changed", "hub-secret"])
def test_upload_failure_keeps_release_row_and_plans_no_paid_trial(tmp_path, monkeypatch, failure):
    from ethevals.hub import upload_hub

    output, task, config = saved_job(tmp_path)
    monkeypatch.setenv("HARBOR_API_KEY", "offline-hub-key")
    folder = output / "jobs/local-name"
    if failure == "missing-key":
        monkeypatch.delenv("HARBOR_API_KEY")
    elif failure == "unchecked":
        (folder / "publication-check.json").unlink()
    elif failure == "withheld":
        (folder / "trial/agent/private").write_text("offline-agent-token")
        check_output(output, {"AGENT_TOKEN": {b"offline-agent-token"}})
    elif failure in {"changed", "hub-secret"}:
        (folder / "trial/agent/private").write_text("offline-hub-key")
        if failure == "hub-secret":
            check_output(output, {})
    commands = []

    def failed(command, **kwargs):
        commands.append(command)
        state = Path(command[2]) / ".harbor-upload"
        state.mkdir()
        (state / "job.tar.gz.tus-url").write_text("offline-hub-key")
        if failure == "timeout":
            assert kwargs.get("timeout") == 600
            raise subprocess.TimeoutExpired(command, 600, output=b"offline-hub-key")
        raise subprocess.CalledProcessError(1, command, output=b"offline-hub-key")

    monkeypatch.setattr("ethevals.hub.subprocess.run", failed)
    upload_hub(output, config)
    assert [(command[:2], Path(command[2]).name, command[3:]) for command in commands] == (
        [(["harbor", "upload"], "local-name", ["--org", "buidlguidl", "--public"])] if failure in {"upload-error", "timeout"} else [])
    rows = recover_rows(output)
    if failure in {"withheld", "hub-secret"}:
        assert (rows[0]["status"], rows[0]["trajectory_url"]) == ("error", None)
    else:
        assert rows[0]["status"] == "passed"
        assert plan([task], config, rows, n_attempts=1)["missing_trials"] == 0
    if failure in {"missing-key", "upload-error", "timeout", "withheld"}:
        release = publish_logs(tmp_path / "release", "owner/repo", "23", "a" * 40, rows=rows)
        if failure == "withheld":
            assert (release["assets"], release["rows"][0]["trajectory_url"]) == ([], None)
        else:
            assert release["rows"][0]["trajectory_url"] == release["assets"][0]["url"]
            assert len(release["assets"]) == 2


@pytest.mark.parametrize("upload", [False, True, "failure"])
def test_local_run_uploads_only_with_flag_and_hides_key_from_agent(tmp_path, monkeypatch, capsys, upload):
    import os
    from harbor.job import Job

    config_path, task = job_config(tmp_path, "api_key"), task_folder(tmp_path)
    config = load_job(config_path)
    config.hub = load_job().hub
    config.agents["local"].name = "oracle"
    config_path.write_text(config.model_dump_json())
    monkeypatch.setenv("HARBOR_API_KEY", "offline-hub-key")
    execution_keys = []

    async def saved_result(job):
        execution_keys.append(os.environ.get("HARBOR_API_KEY"))
        shutil.copytree(Path(__file__).parent / "fixtures/harbor/recorded-trial", job.job_dir / "trial")
        (job.job_dir / "result.json").write_text(json.dumps({"id": JOB_ID}))

    monkeypatch.setattr(Job, "run", saved_result)
    # A stand-in executable avoids replacing other subprocess calls used by Harbor.
    executable = tmp_path / "bin/harbor"
    executable.parent.mkdir()
    executable.write_text("#!/bin/sh\nprintf '%s\\n' \"$@\" > \"$HUB_TEST_ARGS\"\n")
    if upload == "failure":
        executable.write_text(executable.read_text() + "echo offline-hub-key\nexit 1\n")
    executable.chmod(0o755)
    monkeypatch.setenv("PATH", str(executable.parent) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("HUB_TEST_ARGS", str(tmp_path / "upload-args"))
    output = tmp_path / "run"
    assert main(["run", "--config", str(config_path), "--tasks", str(task), "--n-attempts", "1",
                 "--budget", "6", "--rows", str(tmp_path / "none"), "--output", str(output),
                 *(["--upload-hub"] if upload else [])]) == 0
    assert execution_keys == [None]
    assert os.environ["HARBOR_API_KEY"] == "offline-hub-key"
    captured = capsys.readouterr()
    assert "offline-hub-key" not in captured.out + captured.err
    rows = recover_rows(output)
    assert (rows[0]["status"], rows[0]["trajectory_url"]) == (
        "passed", HUB_URL if upload is True else f"/trajectories/{TRIAL_ID}.json")
    if upload:
        arguments = (tmp_path / "upload-args").read_text().splitlines()
        assert (arguments[0], Path(arguments[1]).name, arguments[2:]) == (
            "upload", next((output / "jobs").iterdir()).name, ["--org", "buidlguidl", "--public"])
    else:
        assert not (tmp_path / "upload-args").exists()


@pytest.mark.parametrize("key_env", ["HARBOR_API_KEY", "ARCHIVE_UPLOAD_TOKEN"])
def test_hub_credential_comes_from_config_and_tasks_cannot_request_it(tmp_path, monkeypatch, key_env):
    from ethevals.harbor_tasks import lint_task
    from ethevals.secret_check import secret_values

    task = task_folder(tmp_path)
    config = load_job()
    config.hub.key_env = key_env
    lint_task(task, config)
    monkeypatch.setenv(key_env, "offline-hub-key")
    assert secret_values(config, [task])[key_env] == {b"offline-hub-key"}
    (task / "environment/docker-compose.yaml").write_text(
        'services:\n  browser:\n    environment:\n      KEY: ${' + key_env + ':?Set the key}\n')
    with pytest.raises(ValueError, match=f"{key_env} is a job credential"):
        lint_task(task, config)


def test_ci_upload_command_keeps_hub_links_through_final_publication(tmp_path, monkeypatch):
    import os
    from ethevals.secret_check import stage_artifact
    from support import cli

    output, _, config = saved_job(tmp_path)
    config_path = tmp_path / "upload-config.json"
    config_path.write_text(config.model_dump_json())
    artifact = tmp_path / "download/trial-run-23-1-0"
    stage_artifact(output, output / "public")
    executable = tmp_path / "bin/harbor"
    executable.parent.mkdir()
    executable.write_text("#!/bin/sh\nexit 0\n")
    executable.chmod(0o755)
    monkeypatch.setenv("PATH", str(executable.parent) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("HARBOR_API_KEY", "offline-hub-key")
    assert main(["upload-hub", "--output", str(output), "--config", str(config_path)]) == 0
    assert json.loads((output / "public/rows.jsonl").read_text())["trajectory_url"] == HUB_URL
    shutil.copytree(output / "public", artifact)
    shutil.rmtree(output)
    (artifact / "rows.jsonl").unlink()
    result = cli(Path(__file__).resolve().parents[2] / "scripts/ci.py", "publish-results",
                 "--output", artifact.parent, "--repo", "owner/repo", "--run-id", "23", "--commit", "a" * 40)
    assert result.returncode == 0, result.stderr
    report = json.loads((artifact.parent / "combined/release.json").read_text())
    assert (report["rows"][0]["status"], report["rows"][0]["trajectory_url"]) == ("passed", HUB_URL)
    assert len(report["assets"]) == 2
    assert report["rows"][0] in read_rows(artifact.parent / "combined/rows.jsonl")


def test_upload_step_withholds_a_newly_available_hub_secret_from_artifact(tmp_path, monkeypatch):
    from ethevals.secret_check import stage_artifact

    def refuse_upload(command, **kwargs):
        raise AssertionError("Withheld files cannot reach harbor upload")

    monkeypatch.setattr("ethevals.hub.subprocess.run", refuse_upload)
    output, _, config = saved_job(tmp_path)
    leaked = output / "jobs/local-name/trial/agent/private"
    leaked.write_text("offline-hub-key")
    check_output(output, {})
    stage_artifact(output, output / "public")
    config_path = tmp_path / "upload-config.json"
    config_path.write_text(config.model_dump_json())
    monkeypatch.setenv("HARBOR_API_KEY", "offline-hub-key")
    assert main(["upload-hub", "--output", str(output), "--config", str(config_path)]) == 0
    row = recover_rows(output / "public")[0]
    assert (row["status"], row["error_kind"], row["trajectory_url"]) == ("error", "secret", None)
    assert "HARBOR_API_KEY" in row["error_reason"]
    assert leaked.read_text() == "offline-hub-key"
    assert sorted(path.relative_to(output / "public").as_posix()
                  for path in (output / "public").rglob("*") if path.is_file()) == [
        "jobs/local-name/publication-check.json", "rows.jsonl"]
