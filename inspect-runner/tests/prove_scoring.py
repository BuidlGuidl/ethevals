"""Exercise hostile submissions and a detached writer with real Docker and Forge."""
import argparse
import os
from dataclasses import replace
from pathlib import Path

from inspect_ai import eval, task_with
from inspect_ai.log import read_eval_log
from inspect_ai.scorer import scorer, accuracy
from inspect_ai.solver import solver
from inspect_ai.util import sandbox

from support import fixture_config
from ethevals.files import content_hash
from ethevals.loader import load_eval
from ethevals.rows import export_rows
from support import build_task
from ethevals.preparation import build_images, prepare_compose
from ethevals.sandboxes import runner_exec


@solver
def submit(files, variant):
    async def solve(state, generate):
        source = files["scorer/solution/src/BuilderPoints.sol"]
        if variant == "pragma":
            source = b"pragma solidity =0.8.29; contract BuilderPoints {}"
        elif variant == "missing_method":
            source = b"pragma solidity =0.8.30; contract BuilderPoints {}"
        elif variant == "syntax":
            source = b"pragma solidity =0.8.30; contract BuilderPoints { uint value = ; }"
        elif variant == "traced":
            result = await sandbox().exec(["bash", "-c", """
case $(uname -m) in aarch64) ptrace=117 ;; x86_64) ptrace=101 ;; *) exit 1 ;; esac
nohup perl -e "syscall($ptrace,0,0,0,0); sleep 1000" >/dev/null 2>&1 &
echo $! > /workspace/traced.pid
"""])
            assert result.success, result.stderr
        elif variant == "setup":
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


@scorer(metrics={"*": [accuracy()]})
def traced_process(underlying):
    async def score(state, target):
        result = await underlying(state, target)
        status = await runner_exec(sandbox(), ["/bin/sh", "-c", 'ps -o stat= -p "$(cat /workspace/traced.pid)"'], user="root", cwd="/")
        assert status.stdout.strip().startswith("t"), status
        return result
    return score


def run_proof(output):
    assert not any(os.environ.get(name) for name in ("OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_AUTH_TOKEN"))
    config = fixture_config()
    original = load_eval(Path("evals/building/erc20-points-token"), config)
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
    variants = ("reference", "pragma", "setup", "dependency", "snapshot", "traced", "missing_method", "syntax")
    for variant in variants:
        task = build_task(evaluation, config, None, "internet", "reference", 1, compose)
        task.metadata["epoch"] = list(variants).index(variant) + 1
        task = task_with(task, name=task.name + "-" + variant)
        task.solver = submit(files, variant)
        if variant == "snapshot":
            task.scorer = [frozen_writer(task.scorer[0])]
        elif variant == "traced":
            task.scorer = [traced_process(task.scorer[0])]
        tasks.append(task)
    eval(tasks, log_dir=str(output / "logs"), display="plain", max_tasks=2, max_samples=2,
         retry_on_error=0, fail_on_error=False)
    rows = export_rows(output)
    expected = {"reference": "passed", "pragma": "failed", "setup": "failed", "dependency": "passed", "snapshot": "passed", "traced": "passed", "missing_method": "failed", "syntax": "failed"}
    assert {list(variants)[row["epoch"] - 1]: row["status"] for row in rows} == expected, rows
    assert all(not any("testFree" in name for name in row["checks"]) for row in rows)
    for row in rows:
        log = read_eval_log(str(output / row["log_file"]))
        events = log.samples[0].events
        transfers = [event for event in events if event.event == "sandbox" and event.action == "exec"
                     and "write-submission" in (event.cmd or "")]
        assert len(transfers) == 1
        assert transfers[0].input.startswith("binary ("), "Scorer archive contents entered the public log."
        for event in events:
            if event.event == "sandbox" and event.action == "read_file" and "/out/build-info/" in event.file:
                assert event.output.startswith("binary ("), "Private compiler sources entered the public log."
        assert "PRIVATE_SOURCE_SENTINEL" not in str(log.samples[0].messages)
        assert "PRIVATE_SOURCE_SENTINEL" not in str(row["checks"])
        if list(variants)[row["epoch"] - 1] in {"pragma", "syntax", "missing_method"}:
            assert set(row["checks"]) == {"forge:compile"}
        if list(variants)[row["epoch"] - 1] == "pragma":
            assert "Available solc versions: 0.8.30" in row["checks"]["forge:compile"]["reason"]
        elif list(variants)[row["epoch"] - 1] == "syntax":
            assert row["checks"]["forge:compile"] == {
                "passed": False, "reason": "Error (6933): Expected primary expression."}
        elif list(variants)[row["epoch"] - 1] == "setup":
            assert row["checks"]["forge:test/ImageLibrary.t.sol:ConstructorTest:constructor()"] == {
                "passed": False, "reason": "constructor failed"}
    print("PASS: reference, unavailable compiler, constructor failure, owned libraries, stopped processes, and private diagnostics.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    run_proof(parser.parse_args().output)
