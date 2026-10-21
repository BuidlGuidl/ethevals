from pathlib import Path

import pytest
import yaml

from support import cli


@pytest.fixture
def harbor_task(tmp_path):
    task = tmp_path / "question"
    (task / "environment").mkdir(parents=True)
    (task / "tests").mkdir()
    (task / "solution").mkdir()
    (task / "task.toml").write_text('schema_version = "1.3"\n')
    (task / "instruction.md").write_text("What is the unit?\n")
    (task / "environment/Dockerfile").write_text("FROM debian:bookworm-slim\n")
    (task / "tests/test.sh").write_text("#!/bin/sh\nexit 0\n")
    (task / "solution/solve.sh").write_text("#!/bin/sh\nexit 0\n")
    return task


def test_task_lint_rejects_host_mount(harbor_task):
    compose = harbor_task / "environment/docker-compose.yaml"
    compose.write_text('services:\n  main:\n    volumes: ["/tmp:/data"]\n')
    result = cli("-m", "ethevals.cli", "lint", "--tasks", harbor_task)
    assert result.returncode == 2
    assert "host mounts are forbidden" in result.stderr
    compose.write_text('services:\n  main:\n    volumes: ["data:/data"]\nvolumes:\n  data: {}\n')
    result = cli("-m", "ethevals.cli", "lint", "--tasks", harbor_task)
    assert (result.returncode, result.stdout) == (0, f"{harbor_task}: lint passed\n")


@pytest.mark.parametrize("volume", [
    '"./data:/data"',
    '{type: bind, source: /tmp, target: /data}',
])
def test_task_lint_rejects_other_host_mount_forms(harbor_task, volume):
    (harbor_task / "environment/docker-compose.yaml").write_text(
        f"services:\n  main:\n    volumes: [{volume}]\n"
    )
    result = cli("-m", "ethevals.cli", "lint", "--tasks", harbor_task)
    assert result.returncode == 2
    assert "host mounts are forbidden" in result.stderr


def test_task_lint_rejects_privileged_container(harbor_task):
    (harbor_task / "environment/docker-compose.yaml").write_text(
        "services:\n  browser:\n    image: debian:bookworm-slim\n    privileged: true\n"
    )
    result = cli("-m", "ethevals.cli", "lint", "--tasks", harbor_task)
    assert result.returncode == 2
    assert "service browser: privileged containers are forbidden" in result.stderr


@pytest.mark.parametrize("name", ["instruction.md", "environment/README.md"])
def test_task_lint_rejects_test_words_in_agent_text(harbor_task, name):
    (harbor_task / name).write_text("This is an eval.\n")
    result = cli("-m", "ethevals.cli", "lint", "--tasks", harbor_task)
    assert result.returncode == 2
    assert f"{name}: agent-visible text contains forbidden word 'eval'" in result.stderr


def test_free_check_validates_and_skips_a_task_without_required_env(harbor_task, tmp_path, monkeypatch, capsys):
    from ethevals.cli import main
    from harbor.job import Job

    def refuse_job(*args, **kwargs):
        raise AssertionError("A skipped task cannot start a job.")

    monkeypatch.setattr(Job, "create", refuse_job)
    monkeypatch.delenv("ARCHIVE_RPC_URL", raising=False)
    (harbor_task / "task.toml").write_text(
        'schema_version = "1.3"\n[metadata]\nrequired_env = ["ARCHIVE_RPC_URL"]\n')
    output = tmp_path / "job"
    assert main(["free-check", "--tasks", str(harbor_task), "--output", str(output)]) == 0
    assert capsys.readouterr().out == (
        f"{harbor_task}: lint passed\n"
        f"{harbor_task}: skipped oracle and nop runs because ARCHIVE_RPC_URL is unset.\n")
    assert not output.exists()
    (harbor_task / "instruction.md").write_text("This is an eval.\n")
    with pytest.raises(SystemExit) as error:
        main(["free-check", "--tasks", str(harbor_task), "--output", str(output)])
    assert error.value.code == 2
    assert "forbidden word 'eval'" in capsys.readouterr().err


@pytest.mark.parametrize("value", ['"ARCHIVE_RPC_URL"', '["not a variable"]'])
def test_task_lint_rejects_invalid_required_env(harbor_task, value):
    (harbor_task / "task.toml").write_text(
        f'schema_version = "1.3"\n[metadata]\nrequired_env = {value}\n')
    result = cli("-m", "ethevals.cli", "lint", "--tasks", harbor_task)
    assert result.returncode == 2
    assert "metadata.required_env must list environment variable names" in result.stderr


def test_manual_workflow_requires_secrets_and_selects_declared_tasks(harbor_task, tmp_path, monkeypatch):
    from ethevals import cli as task_cli

    root = Path(__file__).resolve().parents[2]
    workflow = yaml.safe_load((root / ".github/workflows/fork-check.yml").read_text())
    step = next(step for step in workflow["jobs"]["check"]["steps"]
                if step.get("name") == "Run the fork oracle and nop runs")
    script = step["run"].split("\n", 1)[1].rsplit("\nPY", 1)[0]
    (harbor_task / "task.toml").write_text(
        'schema_version = "1.3"\n[metadata]\nrequired_env = ["ARCHIVE_RPC_URL"]\n')
    task = tmp_path / "tasks/question"
    task.parent.mkdir()
    harbor_task.rename(task)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ARCHIVE_RPC_URL", raising=False)
    with pytest.raises(SystemExit, match="Missing ARCHIVE_RPC_URL"):
        exec(script, {})
    calls = []
    monkeypatch.setattr(task_cli, "main", lambda args: calls.append(args) or 17)
    monkeypatch.setenv("ARCHIVE_RPC_URL", "https://archive.example/private-probe")
    with pytest.raises(SystemExit) as error:
        exec(script, {})
    assert error.value.code == 17
    assert calls == [["free-check", "--tasks", str(task), "--output", "results/fork-check"]]


@pytest.mark.docker
def test_free_check_rejects_verifier_that_always_passes(harbor_task, tmp_path):
    (harbor_task / "tests/test.sh").write_text(
        '#!/bin/sh\nset -eu\nmkdir -p /logs/verifier\n'
        'echo \'{"unit":{"passed":true,"reason":"Always passes."}}\' > /logs/verifier/checks.json\n'
        'echo 1 > /logs/verifier/reward.txt\n'
    )
    output = tmp_path / "job"
    result = cli("-m", "ethevals.cli", "free-check", "--tasks", harbor_task, "--output", output)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "nop run must give reward 0 with matching checks" in result.stderr
    assert '"passed":true' in next((output / "nop").glob("*/verifier/checks.json")).read_text()
