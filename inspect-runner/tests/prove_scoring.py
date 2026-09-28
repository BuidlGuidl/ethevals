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

from ethevals.config import load_config
from ethevals.files import content_hash
from ethevals.loader import load_eval
from ethevals.rows import export_rows
from support import build_task
from ethevals.preparation import prepare_eval
from ethevals.sandboxes import runner_exec


@solver
def submit(files, variant):
    async def solve(state, generate):
        source = files["scorer/solution/src/BuilderPoints.sol"]
        if variant == "pragma":
            source = b"pragma solidity =0.8.99; contract BuilderPoints {}"
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


@scorer(metrics=[accuracy()])
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


def run_proof(output):
    assert not any(os.environ.get(name) for name in ("OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_AUTH_TOKEN"))
    config = load_config()
    original = load_eval(Path("evals/building/erc20-points-token"), config)
    files = dict(original.files)
    files["scorer/tests/ImageLibrary.t.sol"] = b'''pragma solidity ^0.8.30;
import {Test} from "forge-std/Test.sol";
contract ImageLibraryTest is Test { function testImageLibrary() public pure { assertTrue(true); } }
'''
    evaluation = prepare_eval(replace(original, files=files, hash=content_hash(files)), output)
    tasks = []
    for variant in ("reference", "pragma", "setup", "dependency", "snapshot"):
        task = build_task(evaluation, config, None, "internet", "reference", 1)
        task.metadata["answer_kind"] = variant
        task = task_with(task, name=task.name + "-" + variant)
        task.solver = submit(files, variant)
        if variant == "snapshot":
            task.scorer = [frozen_writer(task.scorer[0])]
        tasks.append(task)
    eval(tasks, log_dir=str(output / "logs"), display="plain", max_tasks=2, max_samples=2,
         retry_on_error=0, fail_on_error=False)
    rows = export_rows(output)
    expected = {"reference": "passed", "pragma": "failed", "setup": "failed", "dependency": "passed", "snapshot": "passed"}
    assert {row["answer_kind"]: row["status"] for row in rows} == expected, rows
    check_sets = [set(row["checks"]) for row in rows]
    assert all(names == check_sets[0] for names in check_sets)
    assert len(check_sets[0]) == 9
    assert not any("testFree" in name for name in check_sets[0])
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
    print("PASS: reference, invalid pragma, constructor failure, edited image libraries, and frozen detached writer.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    run_proof(parser.parse_args().output)
