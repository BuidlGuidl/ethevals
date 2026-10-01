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
from ethevals.rows import export_rows, results_rows
from ethevals.check_script import run_solution
from ethevals.sandboxes import runner_exec, validate_compose, workspace_files
from ethevals.scorers import FORGE, compiled_sources, prepare_forge, prepare_workspace, run_runner
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
    kwargs.setdefault("timeout", 180)
    return subprocess.run(args, capture_output=True, **kwargs)


class DockerBox:
    def __init__(self, container):
        self.container = container

    async def exec(self, args, user="agent", cwd="/workspace", **kwargs):
        data = kwargs.get("input")
        try:
            result = command(["docker", "exec", "-i", "-u", user, "-w", cwd, self.container, *args],
                             timeout=kwargs.get("timeout", 180),
                             input=data.encode() if isinstance(data, str) else data)
        except subprocess.TimeoutExpired as error:
            raise TimeoutError(f"Docker exec timed out: {error.stderr or error.stdout}") from error
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
    evaluation = load_eval(ROOT / "evals/building/erc20-points-token", fixture_config())
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
    evaluation = load_eval(ROOT / "evals/building/erc20-points-token", fixture_config())
    path = prepare_compose(replace(evaluation, files={**evaluation.files, "compose.yaml": raw}), tmp_path)
    result = command(["docker", "compose", "-f", str(path), "config", "--format", "json"],
                     env={**os.environ, "SECRET_PROBE": "inert-canary"})
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["services"]["extra"]["environment"] == {"TOKEN": "$$SECRET_PROBE"}
    assert path.read_bytes() != raw


def test_snapshot_copies_the_workspace_and_only_solidity_from_npm(tmp_path, monkeypatch):
    import ethevals.sandboxes as sandboxes
    with containers(tmp_path, {"TAR_OPTIONS": "--checkpoint=1 --checkpoint-action=exec=/workspace/probe.sh",
                               "PATH": "/workspace/bin:/usr/bin:/bin"}) as boxes:
        box = boxes["default"]

        async def proof():
            await box.write_file("/workspace/src/cache/X.sol", "contract X {}")
            await box.write_file("/workspace/src/out/Y.sol", "contract Y {}")
            await box.write_file("/workspace/src/Kept.sol", "contract Kept {}")
            await box.write_file("/workspace/packages/app/.git/config", "git internals")
            await box.write_file("/workspace/packages/app/package.json", "{}")
            await box.write_file("/workspace/packages/app/node_modules/@scope/lib/Kept.sol", "library Kept {}")
            await box.write_file("/workspace/packages/app/node_modules/@scope/lib/package.json", "npm metadata")
            await box.write_file("/workspace/packages/app/node_modules/@scope/lib/index.js", "JavaScript")
            await box.write_file("/workspace/probe.sh", "#!/bin/sh\necho root > /tmp/collector-canary\n")
            await box.write_file("/workspace/bin/gzip", "#!/bin/sh\necho gzip > /tmp/collector-canary\nexec /bin/gzip \"$@\"\n")
            setup = await runner_exec(box, ["/bin/sh", "-c", "chmod +x probe.sh bin/gzip; mkdir -p .venv/bin; ln -s /usr/bin/python .venv/bin/python"])
            assert setup.success, setup.stderr
            monkeypatch.setattr(sandboxes, "sandbox", lambda name: box)
            files = await workspace_files()
            assert files == {
                "src/Kept.sol": b"contract Kept {}", "packages/app/package.json": b"{}",
                "packages/app/node_modules/@scope/lib/Kept.sol": b"library Kept {}",
                "probe.sh": b"#!/bin/sh\necho root > /tmp/collector-canary\n",
                "bin/gzip": b"#!/bin/sh\necho gzip > /tmp/collector-canary\nexec /bin/gzip \"$@\"\n",
            }
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
        private = {"scorer/tests/Token.t.sol": b'pragma solidity 0.8.30; import "workspace/src/Token.sol"; contract Check { function testWorks() public pure { assert(true); } }'}

        async def evidence(files):
            root = await prepare_workspace(box, files, private)
            await prepare_forge(root)
            result = await run_runner(FORGE, root)
            assert result.success, result.stderr + result.stdout
            return await compiled_sources(root)

        first = anyio.run(evidence, submitted)
        unused = {f"lib/unused/Unused{n}.sol": b"//" + b"x" * 100000 for n in range(4)}
        second = anyio.run(evidence, {**submitted, **unused})
        assert first == second == {"workspace/src/Token.sol": src, "workspace/lib/custom/Helper.sol": helper}


@solver
def submit(evaluation, variant):
    async def solve(state, generate):
        await run_solution(evaluation, sandbox())
        source = evaluation.files["solution/src/BuilderPoints.sol"]
        if variant == "setup":
            source = source.replace(b"_mint(", b'require(false, "constructor failed"); _mint(')
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


def test_reference_setup_failure_and_frozen_writer(tmp_path):
    output = tmp_path / "proof"
    config = fixture_config()
    original = load_eval(Path("evals/building/erc20-points-token"), config)
    files = dict(original.files)
    files["scorer/tests/ImageLibrary.t.sol"] = b'''pragma solidity ^0.8.30;
import {Test} from "forge-std/Test.sol";
import {BuilderPoints} from "workspace/src/BuilderPoints.sol";
contract ImageLibraryTest is Test { function testImageLibrary() public { assertEq(new BuilderPoints().balanceOf(address(this)), 100_000 * 10 ** 6); } } // PRIVATE_SOURCE_SENTINEL
contract ConstructorTest is Test {
    BuilderPoints token = new BuilderPoints();
    function testConstructed() public view { assertEq(token.totalSupply(), 100_000 * 10 ** 6); }
}
'''
    evaluation = replace(original, files=files, hash=content_hash(files))
    compose = prepare_compose(evaluation, output)
    tasks = []
    expected = {"setup": "failed", "snapshot": "passed"}
    for epoch, variant in enumerate(expected, 1):
        task = build_task(evaluation, config, None, "internet", "reference", 1, compose)
        task.metadata["epoch"] = epoch
        task = task_with(task, name=task.name + "-" + variant)
        task.solver = submit(evaluation, variant)
        if variant == "snapshot":
            task.scorer = [frozen_writer(task.scorer[0])]
        tasks.append(task)
    eval(tasks, log_dir=str(output / "logs"), display="plain", max_tasks=1, max_samples=1,
         retry_on_error=0, fail_on_error=False)
    rows = export_rows(output)
    assert [row["epoch"] for row in rows] == [1, 2]
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
            assert row["checks"]["ConstructorTest.constructor"] == {
                "passed": False, "reason": "constructor failed"}


@pytest.fixture(scope="module", autouse=True)
def stock_images():
    build_images()


def write_workspace(files):
    @solver
    def write():
        async def solve(state, generate):
            for name, data in files.items():
                await sandbox().write_file("/workspace/" + name, data)
            return await generate(state)
        return solve
    return write()


@pytest.mark.parametrize("layout", ["foundry", "hardhat", "fake_test", "unused_broken", "wrong_import", "rejected_config"])
def test_real_scorer_uses_workspace_imports_and_scoped_libraries(tmp_path, layout):
    config = fixture_config()
    original = load_eval(ROOT / "evals/building/erc20-points-token", config)
    submitted = {name.removeprefix("solution/"): data for name, data in original.files.items()
                 if name.startswith("solution/")}
    submitted["foundry.toml"] = original.files["workspace/foundry.toml"]
    files = dict(original.files)
    if layout == "hardhat":
        submitted = {"packages/hardhat/contracts/BuilderPoints.sol": submitted["src/BuilderPoints.sol"],
                     "packages/hardhat/package.json": b"{}", **{
            "packages/hardhat/node_modules/@openzeppelin/contracts/" + name.removeprefix("lib/openzeppelin-contracts/contracts/"): data
            for name, data in submitted.items() if name.startswith("lib/openzeppelin-contracts/contracts/")}}
        files["scorer/tests/BuilderPoints.t.sol"] = files["scorer/tests/BuilderPoints.t.sol"].replace(
            b"workspace/src/BuilderPoints.sol", b"workspace/packages/hardhat/contracts/BuilderPoints.sol")
        files.pop("workspace/foundry.toml")
        files.pop("workspace/src/BuilderPoints.sol")
    elif layout == "fake_test":
        submitted["lib/evil/Test.sol"] = b"contract Test { function assertEq(uint256, uint256, string memory) internal pure {} }"
        submitted["remappings.txt"] += b"forge-std/=lib/evil/\nforge-std/Test.sol=lib/evil/Test.sol\nscorer/tests/:forge-std/=lib/evil/\n"
        submitted["src/BuilderPoints.sol"] = submitted["src/BuilderPoints.sol"].replace(b"_mint(msg.sender, 100_000", b"_mint(msg.sender, 99_999")
    elif layout == "unused_broken":
        submitted["src/Broken.sol"] = b"not Solidity"
        submitted["lib/unrelated/Broken.sol"] = b"not Solidity"
        submitted["src/Binary.sol"] = b"\xff"
        submitted["packages/unused/foundry.toml"] = b"[invalid TOML"
        submitted["packages/rejected/foundry.toml"] = b'[profile.default]\nremappings = ["=lib/x/"]\n'
    elif layout == "rejected_config":
        submitted["foundry.toml"] = b'[profile.default]\nremappings = ["=lib/x/"]\n'
    elif layout == "wrong_import":
        files["scorer/tests/BuilderPoints.t.sol"] = files["scorer/tests/BuilderPoints.t.sol"].replace(
            b"workspace/src/BuilderPoints.sol", b"workspace/src/Missing.sol")
    evaluation = replace(original, files=files, hash=content_hash(files))
    task = build_task(evaluation, config, None, "internet", "reference", 1,
                      prepare_compose(evaluation, tmp_path))
    task.solver = write_workspace(submitted)
    log = eval(task, log_dir=str(tmp_path / "logs"), display="none", retry_on_error=0)[0]
    row = results_rows(log)[0]
    if layout in {"wrong_import", "rejected_config"}:
        assert row["status"] == "failed", row
        assert set(row["checks"]) == {"compile"}
        assert row["checks"]["compile"]["passed"] is False
        assert 'Source "' in row["checks"]["compile"]["reason"]
        assert "not found" in row["checks"]["compile"]["reason"]
    elif layout == "fake_test":
        assert row["checks"]["compile"]["passed"] is True, row
        assert row["checks"]["test_deployer_holds_initial_supply"]["passed"] is False
        assert "total supply" in row["checks"]["test_deployer_holds_initial_supply"]["reason"]
    else:
        assert (row["status"], len(row["checks"])) == ("passed", 11), row
        assert all(check["passed"] is True for check in row["checks"].values())


def test_context_remappings_keep_each_projects_library_private(tmp_path):
    config = fixture_config()
    original = load_eval(ROOT / "evals/building/erc20-points-token", config)
    submitted = {
        "foundry.toml": original.files["workspace/foundry.toml"],
        "remappings.txt": b"../scorer/:scorer/helpers/=lib/evil/\n",
        "lib/evil/AuthorHelper.sol": b'pragma solidity 0.8.30; library AuthorHelper { function value() internal pure returns (uint256) { return 999; } }',
        "packages/first/foundry.toml": b'[profile.default]\nsrc = "src"\nremappings = ["helper/=lib/helper/"]\n',
        "packages/first/src/First.sol": b'pragma solidity 0.8.30; import {Helper} from "helper/Helper.sol"; contract First { function value() external pure returns (uint256) { return Helper.value(); } }',
        "packages/first/lib/helper/Helper.sol": b'pragma solidity 0.8.30; library Helper { function value() internal pure returns (uint256) { return 7; } }',
        "packages/second/package.json": b"{}",
        "packages/second/contracts/Second.sol": b'pragma solidity 0.8.30; import {Helper} from "helper/Helper.sol"; contract Second { function value() external pure returns (uint256) { return Helper.value(); } }',
        "packages/second/node_modules/helper/Helper.sol": b'pragma solidity 0.8.30; library Helper { function value() internal pure returns (uint256) { return 42; } }',
    }
    tests = b'''pragma solidity 0.8.30;
import {Test} from "forge-std/Test.sol";
import {First} from "workspace/packages/first/src/First.sol";
import {Second} from "workspace/packages/second/contracts/Second.sol";
import {AuthorHelper} from "../helpers/AuthorHelper.sol";
contract ScopedLibrariesTest is Test {
    function test_first_library() public { assertEq(new First().value(), 7, "first library"); }
    function test_second_library() public { assertEq(new Second().value(), 42, "second library"); }
    function test_author_helper() public pure { assertEq(AuthorHelper.value(), 99, "author helper"); }
}
'''
    files = {**original.files, "scorer/tests/BuilderPoints.t.sol": tests,
             "scorer/helpers/AuthorHelper.sol": b'pragma solidity 0.8.30; library AuthorHelper { function value() internal pure returns (uint256) { return 99; } }'}
    evaluation = replace(original, files=files, hash=content_hash(files))
    task = build_task(evaluation, config, None, "internet", "reference", 1, prepare_compose(evaluation, tmp_path))
    task.solver = write_workspace(submitted)
    log = eval(task, log_dir=str(tmp_path / "logs"), display="none", retry_on_error=0)[0]
    assert results_rows(log)[0]["checks"] == {
        "compile": {"passed": True, "reason": "Compilation passed."},
        "test_first_library": {"passed": True, "reason": "Test passed."},
        "test_second_library": {"passed": True, "reason": "Test passed."},
        "test_author_helper": {"passed": True, "reason": "Test passed."},
    }
