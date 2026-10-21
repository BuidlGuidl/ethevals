import pytest

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
