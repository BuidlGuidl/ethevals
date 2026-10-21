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
    assert "service browser: forbidden options ['privileged']" in result.stderr


@pytest.mark.parametrize("key,value", [
    ("pid", "host"), ("network_mode", "host"), ("ipc", "host"),
    ("cap_add", ["SYS_PTRACE"]), ("devices", ["/dev/mem"]),
    ("security_opt", ["apparmor:unconfined"]), ("userns_mode", "host"),
    ("extends", "other.yaml"), ("volumes_from", ["other"]),
    ("env_file", "/etc/environment"), ("future_option", True),
])
def test_task_lint_rejects_service_options_outside_allowlist(harbor_task, key, value):
    from ethevals.harbor_tasks import lint_task

    (harbor_task / "environment/docker-compose.yaml").write_text(
        yaml.safe_dump({"services": {"browser": {"image": "debian:bookworm-slim", key: value}}}))
    with pytest.raises(ValueError, match=f"service browser: forbidden options .*{key}"):
        lint_task(harbor_task)


@pytest.mark.parametrize("value", [
    "${HOST_SECRET}", "$HOST_SECRET", "${ARCHIVE_RPC_URL:-${HOST_SECRET}}",
])
def test_task_lint_rejects_undeclared_interpolation(harbor_task, value):
    from ethevals.harbor_tasks import lint_task

    (harbor_task / "task.toml").write_text(
        'schema_version = "1.3"\n[metadata]\nrequired_env = ["ARCHIVE_RPC_URL"]\n')
    (harbor_task / "environment/docker-compose.yaml").write_text(yaml.safe_dump({
        "services": {"browser": {"environment": {"URL": value}}}}))
    with pytest.raises(ValueError, match="HOST_SECRET.*metadata.required_env"):
        lint_task(harbor_task)


def test_task_lint_accepts_declared_interpolation_and_container_dollars(harbor_task):
    from ethevals.cli import main

    (harbor_task / "task.toml").write_text(
        'schema_version = "1.3"\n[metadata]\nrequired_env = ["ARCHIVE_RPC_URL"]\n')
    (harbor_task / "environment/docker-compose.yaml").write_text(yaml.safe_dump({"services": {
        "browser": {"build": ".", "environment": {"URL": "${ARCHIVE_RPC_URL:?required}"},
                    "command": "echo $$CONTAINER_VAR"}}}))
    assert main(["lint", "--tasks", str(harbor_task)]) == 0


@pytest.mark.parametrize("environment", [["HOST_SECRET"], {"HOST_SECRET": None}])
def test_task_lint_rejects_implicit_host_environment(harbor_task, environment):
    from ethevals.harbor_tasks import lint_task

    (harbor_task / "environment/docker-compose.yaml").write_text(yaml.safe_dump({
        "services": {"browser": {"environment": environment}}}))
    with pytest.raises(ValueError, match="explicit.*environment"):
        lint_task(harbor_task)


@pytest.mark.parametrize("network", [
    {"external": True, "name": "host"}, {"driver": "host"},
    {"external": True, "name": "${NETWORK_NAME}"},
])
def test_task_lint_rejects_host_network_definitions(harbor_task, network):
    from ethevals.harbor_tasks import lint_task

    (harbor_task / "task.toml").write_text(
        'schema_version = "1.3"\n[metadata]\nrequired_env = ["NETWORK_NAME"]\n')
    (harbor_task / "environment/docker-compose.yaml").write_text(yaml.safe_dump({
        "services": {"browser": {"networks": ["outside"]}}, "networks": {"outside": network}}))
    with pytest.raises(ValueError, match="network outside: host networks and network driver options are forbidden"):
        lint_task(harbor_task)


def test_task_lint_accepts_an_external_bridge(harbor_task):
    from ethevals.cli import main

    (harbor_task / "environment/docker-compose.yaml").write_text(yaml.safe_dump({
        "services": {"browser": {"networks": ["upstream"]}},
        "networks": {"upstream": {"external": True, "name": "task-upstream"}}}))
    assert main(["lint", "--tasks", str(harbor_task)]) == 0


def test_task_lint_accepts_all_real_tasks(capsys):
    from ethevals.cli import main

    paths = sorted((Path(__file__).resolve().parents[2] / "tasks").glob("*/*/task.toml"))
    assert main(["lint", "--tasks", *(str(path.parent) for path in paths)]) == 0
    assert capsys.readouterr().out == "".join(f"{path.parent}: lint passed\n" for path in paths)


@pytest.mark.parametrize("build", [
    "../../shared",
    '{context: ., dockerfile: ../../Dockerfile}',
    '{context: ., additional_contexts: {files: ../../shared}}',
    '{context: ., additional_contexts: [files=../../shared]}',
])
def test_task_lint_keeps_build_inputs_inside_the_folder(harbor_task, build):
    compose = harbor_task / "environment/docker-compose.yaml"
    compose.write_text(f"services:\n  main:\n    build: {build}\n")
    result = cli("-m", "ethevals.cli", "lint", "--tasks", harbor_task)
    assert result.returncode == 2
    assert "build inputs must stay inside the task folder" in result.stderr
    compose.write_text("services:\n  main:\n    build: .\n")
    result = cli("-m", "ethevals.cli", "lint", "--tasks", harbor_task)
    assert (result.returncode, result.stdout) == (0, f"{harbor_task}: lint passed\n")


@pytest.mark.parametrize("options", [
    {"privileged": True}, {"network": "host"}, {"entitlements": ["security.insecure"]},
    {"ssh": ["default"]}, {"secrets": ["host-secret"]},
])
def test_task_lint_rejects_build_options_that_expose_the_host(harbor_task, options):
    from ethevals.harbor_tasks import lint_task

    (harbor_task / "environment/docker-compose.yaml").write_text(yaml.safe_dump({
        "services": {"browser": {"build": {"context": ".", **options}}}}))
    with pytest.raises(ValueError, match="forbidden build options"):
        lint_task(harbor_task)


@pytest.mark.parametrize("arguments", [["HOST_SECRET"], {"HOST_SECRET": None}])
def test_task_lint_rejects_implicit_host_build_arguments(harbor_task, arguments):
    from ethevals.harbor_tasks import lint_task

    (harbor_task / "environment/docker-compose.yaml").write_text(yaml.safe_dump({
        "services": {"browser": {"build": {"context": ".", "args": arguments}}}}))
    with pytest.raises(ValueError, match="explicit values for build arguments"):
        lint_task(harbor_task)


def test_task_lint_rejects_interpolation_in_build_paths(harbor_task, monkeypatch):
    from ethevals.harbor_tasks import lint_task

    (harbor_task / "task.toml").write_text(
        'schema_version = "1.3"\n[metadata]\nrequired_env = ["BUILD_ROOT"]\n')
    monkeypatch.setenv("BUILD_ROOT", "/")
    (harbor_task / "environment/docker-compose.yaml").write_text(yaml.safe_dump({
        "services": {"browser": {"build": {"context": "${BUILD_ROOT}"}}}}))
    with pytest.raises(ValueError, match="build paths must be literal"):
        lint_task(harbor_task)


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
