from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
import json
import os
import subprocess
import uuid

from ethevals.files import content_hash
from ethevals.loader import load_eval
from ethevals.preparation import build_images, prepare_compose
from ethevals.rows import export_rows
from ethevals.sandboxes import runner_exec, validate_compose, workspace_files
from ethevals.scorers import compiled_sources, forge, prepare_forge
from inspect_ai import eval, task_with
from inspect_ai.log import read_eval_log
from inspect_ai.scorer import accuracy, scorer
from inspect_ai.solver import solver
from inspect_ai.util import ExecResult, sandbox
import anyio
import pytest
import yaml

from support import build_task, fixture_config


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
    evaluation = load_eval(ROOT / "inspect-runner/tests/fixtures/building/erc20-points-token", fixture_config())
    path = prepare_compose(evaluation, tmp_path)
    data = yaml.safe_load(path.read_bytes())
    for service in data["services"].values():
        service["environment"] = environment or {}
    path.write_text(yaml.safe_dump(data))
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
    data = {"services": {"extra": {"image": "postgres:17", "mem_limit": "512m", "environment": {"TOKEN": b"$SECRET_PROBE"}}}}
    with pytest.raises(ValueError, match="unsupported YAML scalar"):
        validate_compose(tmp_path / "binary.yaml", data=yaml.safe_dump(data).encode())
    data["services"]["extra"]["environment"] = {"TOKEN": "$$SECRET_PROBE"}
    raw = yaml.safe_dump(data).encode() + b"# author comment\n"
    evaluation = load_eval(ROOT / "inspect-runner/tests/fixtures/building/erc20-points-token", fixture_config())
    path = prepare_compose(replace(evaluation, files={**evaluation.files, "compose.yaml": raw}), tmp_path)
    result = command(["docker", "compose", "-f", str(path), "config", "--format", "json"],
                     env={**os.environ, "SECRET_PROBE": "inert-canary"})
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["services"]["extra"]["environment"] == {"TOKEN": "$$SECRET_PROBE"}
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
            result = await forge(box, timeout=180)
            assert result.success, result.stderr + result.stdout
            return await compiled_sources(box)

        first = anyio.run(evidence, submitted)
        unused = {f"lib/unused/Unused{n}.sol": b"//" + b"x" * 100000 for n in range(4)}
        second = anyio.run(evidence, {**submitted, **unused})
        assert first == second == {"src/Token.sol": src, "lib/custom/Helper.sol": helper}


@solver
def submit(reference, variant):
    async def solve(state, generate):
        source = reference
        if variant == "setup":
            source = source.replace(b"_mint(", b'require(false, "constructor failed"); _mint(')
        elif variant == "dependency":
            await sandbox().write_file("/workspace/lib/openzeppelin-contracts/contracts/token/ERC20/ERC20.sol", "invalid Solidity")
            await sandbox().write_file("/workspace/lib/forge-std/src/Test.sol", "invalid Solidity")
            source += b"\ncontract Extra { function testFree() public {} }\n"
        elif variant == "snapshot":
            result = await sandbox().exec(["bash", "-c", """
mkdir /tmp/ethevals-workspace.tar.gz
printf '// initial\n' > /workspace/src/Counter.sol
nohup sh -c 'i=0; while true; do i=$((i+1)); printf "// %s\n" "$i" > /workspace/src/Counter.sol; sleep 0.05; done' >/dev/null 2>&1 &
echo $! > /workspace/writer.pid
"""])
            assert result.success, result.stderr
        await sandbox().write_file("/workspace/src/BuilderPoints.sol", source)
        return await generate(state)
    return solve


@scorer(metrics={"*": [accuracy()]})
def frozen_writer(underlying):
    async def score(state, target):
        result = await underlying(state, target)
        box = sandbox()
        before = await box.read_file("/workspace/src/Counter.sol")
        await runner_exec(box, ["/usr/bin/sleep", "0.2"], user="root", cwd="/")
        after = await box.read_file("/workspace/src/Counter.sol")
        assert before == after, (before, after)
        status = await runner_exec(box, ["/bin/sh", "-c", 'ps -o stat= -p "$(cat /workspace/writer.pid)"'], user="root", cwd="/")
        assert status.stdout.strip().startswith("T"), status
        return result
    return score


def test_reference_failures_owned_libraries_and_frozen_writer(tmp_path):
    output = tmp_path / "proof"
    config = fixture_config()
    original = load_eval(Path("inspect-runner/tests/fixtures/building/erc20-points-token"), config)
    files = dict(original.files)
    files["scorer/tests/ImageLibrary.t.sol"] = b'''pragma solidity ^0.8.30;
import {Test} from "forge-std/Test.sol";
import {BuilderPoints} from "../src/BuilderPoints.sol";
contract ImageLibraryTest is Test { function testImageLibrary() public { assertEq(new BuilderPoints().balanceOf(address(this)), 1_000_000 ether); } } // PRIVATE_SOURCE_SENTINEL
contract ConstructorTest is Test {
    BuilderPoints token = new BuilderPoints();
    function testConstructed() public view { assertEq(token.totalSupply(), 1_000_000 ether); }
}
'''
    build_images()
    evaluation = replace(original, files=files, hash=content_hash(files))
    compose = prepare_compose(evaluation, output)
    tasks = []
    expected = {"setup": "failed", "dependency": "passed", "snapshot": "passed"}
    for epoch, variant in enumerate(expected, 1):
        task = build_task(evaluation, config, None, "internet", "reference", 1, compose)
        task.metadata["epoch"] = epoch
        task = task_with(task, name=task.name + "-" + variant)
        task.solver = submit(files["scorer/solution/src/BuilderPoints.sol"], variant)
        if variant == "snapshot":
            task.scorer = [frozen_writer(task.scorer[0])]
        tasks.append(task)
    eval(tasks, log_dir=str(output / "logs"), display="plain", max_tasks=2, max_samples=2,
         retry_on_error=0, fail_on_error=False)
    rows = export_rows(output)
    assert [row["epoch"] for row in rows] == [1, 2, 3]
    assert all(not any("testFree" in name for name in row["checks"]) for row in rows)
    for row in rows:
        variant = list(expected)[row["epoch"] - 1]
        assert row["status"] == expected[variant], row
        log = read_eval_log(str(output / row["log_file"]))
        assert "PRIVATE_SOURCE_SENTINEL" not in log.model_dump_json()
        events = log.samples[0].events
        transfers = [event for event in events if event.event == "sandbox" and event.action == "exec"
                     and "write-submission" in (event.cmd or "")]
        assert len(transfers) == 1
        assert transfers[0].input.startswith("binary ("), "Scorer archive contents entered the public log."
        for event in events:
            if event.event == "sandbox" and event.action == "read_file" and "/out/build-info/" in event.file:
                assert event.output.startswith("binary ("), "Private compiler sources entered the public log."
        if variant == "setup":
            assert row["checks"]["forge:test/ImageLibrary.t.sol:ConstructorTest:constructor()"] == {
                "passed": False, "reason": "constructor failed"}
