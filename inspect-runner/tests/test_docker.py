"""Real container proofs. Run with pytest --run-docker -m docker."""
import json
import os
import subprocess
import uuid
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

import anyio
import pytest
import yaml
from inspect_ai.util import ExecResult

from ethevals.config import load_config
from ethevals.loader import load_eval
from ethevals.preparation import prepare_compose
from ethevals.sandboxes import IMAGES, runner_exec, validate_compose, workspace_files
from ethevals.scorers import compiled_sources, forge, forge_checks, prepare_forge, rubric_evidence
from prove_scoring import run_proof

pytestmark = pytest.mark.docker
ROOT = Path(__file__).resolve().parents[2]


def command(args, **kwargs):
    return subprocess.run(args, capture_output=True, timeout=180, **kwargs)


class DockerBox:
    def __init__(self, container):
        self.container = container

    async def exec(self, args, user="agent", cwd="/workspace", **kwargs):
        data = kwargs.get("input")
        result = command(["docker", "exec", "-i", "-u", user, "-w", cwd, self.container, *args],
                         input=data.encode() if isinstance(data, str) else data)
        return ExecResult(success=result.returncode == 0, returncode=result.returncode,
                          stdout=result.stdout.decode(), stderr=result.stderr.decode())

    async def read_file(self, path, text=True):
        result = command(["docker", "exec", "-u", "root", self.container, "/usr/bin/env", "-i", "/bin/cat", path])
        assert result.returncode == 0, result.stderr
        return result.stdout.decode() if text else result.stdout

    async def write_file(self, path, data):
        await runner_exec(self, ["/bin/mkdir", "-p", str(Path(path).parent)])
        result = command(["docker", "exec", "-i", "-u", "agent", self.container,
                          "/usr/bin/env", "-i", "/usr/bin/tee", path],
                         input=data.encode() if isinstance(data, str) else data)
        assert result.returncode == 0, result.stderr


@contextmanager
def containers(tmp_path, environment=None):
    assert not any(os.environ.get(name) for name in (
        "OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_AUTH_TOKEN"))
    data = yaml.safe_load((IMAGES / "stock.compose.yaml").read_bytes())
    data["services"]["default"].pop("build")
    for service in data["services"].values():
        service["environment"] = environment or {}
    evaluation = load_eval(ROOT / "evals/building/erc20-points-token", load_config())
    evaluation = replace(evaluation, files={**evaluation.files, "compose.yaml": yaml.safe_dump(data).encode()})
    path = prepare_compose(evaluation, tmp_path)
    prefix = ["docker", "compose", "-p", "proof-" + uuid.uuid4().hex[:12], "-f", str(path)]
    try:
        result = command([*prefix, "up", "-d"])
        assert result.returncode == 0, result.stderr
        boxes = {name: DockerBox(command([*prefix, "ps", "-q", name]).stdout.decode().strip()) for name in ("default", "scorer")}
        yield boxes
    finally:
        result = command([*prefix, "down", "--volumes"])
        assert result.returncode == 0, result.stderr


def test_compose_sees_only_the_normalized_document(tmp_path):
    data = yaml.safe_load((IMAGES / "stock.compose.yaml").read_bytes())
    data["services"]["default"].pop("build")
    data["services"]["default"]["environment"] = {"TOKEN": b"$SECRET_PROBE"}
    with pytest.raises(ValueError, match="unsupported YAML scalar"):
        validate_compose(tmp_path / "binary.yaml", data=yaml.safe_dump(data).encode())
    data["services"]["default"]["environment"] = {"TOKEN": "$$SECRET_PROBE"}
    raw = yaml.safe_dump(data).encode() + b"# author comment\n"
    evaluation = load_eval(ROOT / "evals/building/erc20-points-token", load_config())
    path = prepare_compose(replace(evaluation, files={**evaluation.files, "compose.yaml": raw}), tmp_path)
    result = command(["docker", "compose", "-f", str(path), "config", "--format", "json"],
                     env={**os.environ, "SECRET_PROBE": "inert-canary"})
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["services"]["default"]["environment"] == {"TOKEN": "$$SECRET_PROBE"}
    assert path.read_bytes() != raw


def test_snapshot_ignores_unread_trees_and_clears_root_environment(tmp_path, monkeypatch):
    import ethevals.sandboxes as sandboxes
    with containers(tmp_path, {"TAR_OPTIONS": "--checkpoint=1 --checkpoint-action=exec=/workspace/probe.sh",
                               "PATH": "/workspace/bin:/usr/bin:/bin"}) as boxes:
        box = boxes["default"]

        async def proof():
            await box.write_file("/workspace/src/cache/X.sol", "contract X {}")
            await box.write_file("/workspace/src/out/Y.sol", "contract Y {}")
            await box.write_file("/workspace/probe.sh", "#!/bin/sh\necho root > /tmp/collector-canary\n")
            await box.write_file("/workspace/bin/gzip", "#!/bin/sh\necho gzip > /tmp/collector-canary\nexec /bin/gzip \"$@\"\n")
            setup = await runner_exec(box, ["/bin/sh", "-c", "chmod +x probe.sh bin/gzip; mkdir -p .venv/bin; ln -s /usr/bin/python .venv/bin/python"])
            assert setup.success, setup.stderr
            monkeypatch.setattr(sandboxes, "sandbox", lambda name: box)
            files = await workspace_files()
            assert files == {"src/cache/X.sol": b"contract X {}", "src/out/Y.sol": b"contract Y {}"}
            canary = await runner_exec(box, ["/usr/bin/test", "-e", "/tmp/collector-canary"], user="root")
            assert canary.returncode == 1
        anyio.run(proof)


def test_unused_library_does_not_change_compiled_rubric_evidence(tmp_path):
    with containers(tmp_path, {"TAR_OPTIONS": "--checkpoint=1 --checkpoint-action=exec=/workspace/probe.sh",
                               "PATH": "/workspace/bin:/usr/bin:/bin", "FOUNDRY_FFI": "true"}) as boxes:
        box = boxes["scorer"]
        src = b'pragma solidity ^0.8.30; import "../lib/custom/Helper.sol"; contract Token {}'
        helper = b"pragma solidity ^0.8.30; library Helper {}"
        submitted = {"src/Token.sol": src, "lib/custom/Helper.sol": helper}
        private = {"scorer/tests/Token.t.sol": b'pragma solidity ^0.8.30; import "../src/Token.sol"; contract Check { function testWorks() public pure { assert(true); } }'}

        async def evidence(files):
            await prepare_forge(box, files, private)
            result = await forge(box)
            assert result.success, result.stderr + result.stdout
            return rubric_evidence(await compiled_sources(box, files))

        first = anyio.run(evidence, submitted)
        unused = {f"lib/unused/Unused{n}.sol": b"//" + b"x" * 100000 for n in range(4)}
        second = anyio.run(evidence, {**submitted, **unused})
        assert first == second == ({"src/Token.sol": src.decode(), "lib/custom/Helper.sol": helper.decode()}, [])
        assert list(second[0]) == ["src/Token.sol", "lib/custom/Helper.sol"]


def test_reference_failures_owned_libraries_and_frozen_writer(tmp_path):
    run_proof(tmp_path / "proof")


def test_unavailable_compiler_fails_offline_and_names_available_versions(tmp_path):
    with containers(tmp_path) as boxes:
        box = boxes["scorer"]
        details = json.loads(command(["docker", "inspect", box.container]).stdout)[0]
        networks = list(details["NetworkSettings"]["Networks"])
        assert len(networks) == 1
        assert json.loads(command(["docker", "network", "inspect", networks[0]]).stdout)[0]["Internal"] is True

        async def proof():
            installed = await runner_exec(box, ["/bin/sh", "-c", "ls /home/agent/.svm/*/solc-*"])
            assert installed.stdout.strip() == "/home/agent/.svm/0.8.30/solc-0.8.30"
            await prepare_forge(box, {"src/Token.sol": b"pragma solidity =0.8.29; contract Token {}"}, {
                "scorer/tests/Token.t.sol": b'pragma solidity ^0.8.0; import "../src/Token.sol"; contract Tests { function testToken() public { new Token(); } }'})
            result = await forge(box)
            checks = forge_checks(result.stdout, result.stderr, result.returncode, ["forge:test/Token.t.sol:Tests:testToken()"])
            assert checks["forge:compile"]["passed"] is False
            assert "Available solc versions: 0.8.30" in checks["forge:compile"]["reason"]
            assert "No solc version installed that matches" in result.stderr
            assert "https://" not in result.stderr
        anyio.run(proof)


def test_slow_output_consumer_cannot_truncate_forge(tmp_path, monkeypatch):
    import ethevals.scorers as scorers
    original = scorers.runner_exec
    with containers(tmp_path) as boxes:
        box = boxes["scorer"]

        async def slow_consumer(box, args, **kwargs):
            args = [arg.replace("/usr/bin/head", "/tmp/slow-head") for arg in args]
            return await original(box, args, **kwargs)

        async def proof():
            await box.write_file("/tmp/slow-head", '#!/bin/sh\nsleep 1\nexec /usr/bin/head "$@"\n')
            await runner_exec(box, ["/bin/chmod", "+x", "/tmp/slow-head"])
            await prepare_forge(box, {"src/Token.sol": b"pragma solidity =0.8.30; contract Token {}"}, {
                "scorer/tests/Token.t.sol": b"pragma solidity =0.8.30; contract Tests { function testToken() public pure { assert(true); } }"})
            monkeypatch.setattr(scorers, "runner_exec", slow_consumer)
            result = await forge(box)
            assert forge_checks(result.stdout, result.stderr, result.returncode,
                                ["forge:test/Token.t.sol:Tests:testToken()"]) == {
                "forge:compile": {"passed": True, "reason": "Compilation passed."},
                "forge:test/Token.t.sol:Tests:testToken()": {"passed": True, "reason": "Test passed."},
            }
        anyio.run(proof)


def test_forge_output_file_has_a_size_cap(tmp_path, monkeypatch):
    import ethevals.scorers as scorers
    from inspect_ai.util import OutputLimitExceededError
    original = scorers.runner_exec
    with containers(tmp_path) as boxes:
        async def noisy_forge(box, args, **kwargs):
            position = args.index("/usr/local/bin/forge")
            args = args[:position] + ["/usr/bin/perl", "-e", 'print "x" x (12 * 1024 * 1024)']
            return await original(box, args, **kwargs)

        async def proof():
            monkeypatch.setattr(scorers, "runner_exec", noisy_forge)
            with pytest.raises(OutputLimitExceededError, match="10 MiB"):
                await forge(boxes["scorer"])
            assert len(await boxes["scorer"].read_file("/tmp/forge.stdout", text=False)) == 10485761
        anyio.run(proof)
