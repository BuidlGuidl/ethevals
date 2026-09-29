from support import fixture_config
from dataclasses import replace
from ethevals.checks import check_agent, check_grader
from ethevals.loader import load_eval
from ethevals.preparation import build_images, prepare_compose
from ethevals.rows import export_rows, results_rows
from ethevals.runner import build_task
from ethevals.sandboxes import runner_exec
from inspect_ai import eval
from inspect_ai.log import read_eval_log
from inspect_ai.solver import solver
from inspect_ai.util import sandbox
from pathlib import Path
import anyio
import pytest


pytestmark = pytest.mark.docker
ROOT = Path(__file__).resolve().parents[2]


@solver
def slow_agent():
    async def solve(state, generate):
        await anyio.sleep(1)
        return await generate(state)
    return solve


def test_slow_setup_preserves_agent_time(tmp_path):
    config = fixture_config()
    evaluation = load_eval(ROOT / "evals/transactions/send-six-decimal-token", config)
    files = {**evaluation.files,
             "scorer/setup.sh": b'#!/usr/bin/env python3\nimport time; time.sleep(31); print(\'{"files": {}}\')',
             "scorer/check.py": b'#!/usr/bin/env python3\nprint(\'{"ran":{"passed":true,"reason":"Agent reached grading."}}\')'}
    evaluation = replace(evaluation, files=files)
    compose = prepare_compose(evaluation, tmp_path)
    agent = replace(check_agent(evaluation, "empty"), solver_for=lambda _: slow_agent())
    task = build_task(evaluation, config, agent, check_grader(), "internet", 1, compose)
    task.working_limit = 2
    # Setup exceeds both agent limits. The wall limit also gives scoring
    # 15 seconds instead of a flaky one-second Docker capture deadline.
    task.time_limit = 30
    log = eval(task, log_dir=str(tmp_path / "slow"), display="none", retry_on_error=0)[0]
    row = results_rows(log)[0]
    assert (row["status"], row["checks"]) == ("passed", {"script:ran": {"passed": True, "reason": "Agent reached grading."}})
    assert row["total_tokens"] > 0


@solver
def attempt(evaluation, variant):
    async def solve(state, generate):
        box = sandbox("default")
        source = evaluation.files["scorer/solution/run.sh"]
        if variant in {"reference", "wrong"}:
            if variant == "wrong":
                source = source.replace(b"125 * 10 ** decimals / 10", b"13 * 10 ** decimals")
            await box.write_file("/workspace/run.sh", source)
            result = await runner_exec(box, ["/bin/bash", "/workspace/run.sh"], timeout=60)
            assert result.success, result.stderr
        elif variant == "crash":
            await sandbox("chain").write_file("/eval/scorer/check.py", b"#!/usr/bin/env python3\nraise RuntimeError('crash proof')\n")
        elif variant == "missing":
            await sandbox("chain").write_file("/eval/scorer/check.py", b'#!/usr/bin/env python3\nprint(\'{"recipient_balance":{"passed":false,"reason":"Missing sender proof."}}\')\n')
        elif variant == "cheat":
            result = await runner_exec(box, ["/bin/bash", "-c", """
set -eu
read_value() { sed -n 's/.*"'"$1"'": "\\([^"]*\\)".*/\\1/p' /workspace/chain.json; }
sender=$(read_value sender)
token=$(read_value token)
recipient=$(read_value recipient)
data=$(cast calldata 'transfer(address,uint256)' "$recipient" 12500000)
transaction="{\\"from\\":\\"$sender\\",\\"to\\":\\"$token\\",\\"data\\":\\"$data\\",\\"gas\\":\\"0x186a0\\"}"
for method in eth_sendTransaction eth_sendUnsignedTransaction; do
    curl -sS -H 'Content-Type: application/json' --data "{\\"jsonrpc\\":\\"2.0\\",\\"id\\":1,\\"method\\":\\"$method\\",\\"params\\":[$transaction]}" http://chain:8545
done
curl -sS -H 'Content-Type: application/json' --data "{\\"jsonrpc\\":\\"2.0\\",\\"id\\":1,\\"method\\":\\"anvil_setBalance\\",\\"params\\":[\\"$recipient\\",\\"0xffff\\"]}" http://chain:8545
curl -sS -H 'Content-Type: application/json' --data "[{\\"jsonrpc\\":\\"2.0\\",\\"id\\":1,\\"method\\":\\"eth_chainId\\"},{\\"jsonrpc\\":\\"2.0\\",\\"id\\":2,\\"method\\":\\"eth_sendUnsignedTransaction\\",\\"params\\":[$transaction]}]" http://chain:8545
curl -sS -H 'Connection: Upgrade' -H 'Upgrade: websocket' http://chain:8545
if curl -sS --connect-timeout 2 http://chain:8546; then exit 1; fi
"""])
            assert result.success, result.stderr
            assert result.stdout.count("-32601") == 5
            assert "405" in result.stdout
        elif variant == "pending":
            # Queue a signed future-nonce transfer. Capture must not mine it.
            source = source.replace(b"cast send \"$token\"", b"cast send --async --nonce 1 \"$token\"")
            await box.write_file("/workspace/run.sh", source)
            result = await runner_exec(box, ["/bin/bash", "/workspace/run.sh"], timeout=60)
            assert result.success, result.stderr
            # Keep trying the valid transfer after the solver returns.
            await box.write_file("/workspace/run.sh", evaluation.files["scorer/solution/run.sh"])
            result = await runner_exec(box, ["/bin/bash", "-c", "nohup bash -c 'sleep 3; bash /workspace/run.sh' >/tmp/writer.log 2>&1 </dev/null &"])
            assert result.success
            original = evaluation.files["scorer/check.py"]
            probe = b"""#!/usr/bin/env python3
import sys, time
sys.path.insert(0, '/opt')
from rpc_filter import rpc
before = rpc('eth_getBlockByNumber', ['latest', False])['hash']
time.sleep(4)
assert rpc('eth_getBlockByNumber', ['latest', False])['hash'] == before
"""
            await sandbox("chain").write_file("/eval/scorer/check.py", probe + original)
        return await generate(state)
    return solve


def test_act_checks_bypasses_and_grading_boundary(tmp_path):
    output = tmp_path / "chain"
    config = fixture_config()
    root = Path(__file__).resolve().parents[2]
    evaluation = load_eval(root / "evals/transactions/send-six-decimal-token", config)
    build_images()
    compose = prepare_compose(evaluation, output)
    tasks = []
    variants = ("reference", "wrong", "crash", "missing", "cheat", "pending")
    for variant in variants:
        agent = check_agent(evaluation, "empty")
        agent = replace(agent, metadata={**agent.metadata, "epoch": list(variants).index(variant) + 1},
                         solver_for=lambda _, variant=variant: attempt(evaluation, variant))
        tasks.append(build_task(evaluation, config, agent, check_grader(), "internet", 1, compose))
    eval(tasks, log_dir=str(output / "logs"), display="plain", retry_on_error=0, fail_on_error=False, max_tasks=2)
    rows = export_rows(output)
    for row in rows:
        assert row["status"] == ("passed" if list(variants)[row["epoch"] - 1] == "reference" else
                                 "error" if list(variants)[row["epoch"] - 1] == "crash" else "failed"), row
        names = (set() if list(variants)[row["epoch"] - 1] == "crash" else
                 {"script:recipient_balance"} if list(variants)[row["epoch"] - 1] == "missing" else
                 {"script:agent_sender", "script:recipient_balance"})
        assert set(row["checks"]) == names
        if list(variants)[row["epoch"] - 1] == "wrong":
            assert row["checks"]["script:recipient_balance"] == {"passed": False, "reason": "Recipient holds 13000000 base units; expected 12500000."}
        if list(variants)[row["epoch"] - 1] == "pending":
            assert row["checks"]["script:recipient_balance"] == {"passed": False, "reason": "Recipient holds 0 base units; expected 12500000."}
        if list(variants)[row["epoch"] - 1] == "cheat":
            log = read_eval_log(str(output / row["log_file"]))
            text = log.model_dump_json()
            for method in ("eth_sendTransaction", "eth_sendUnsignedTransaction", "anvil_setBalance", "HTTP GET"):
                assert f"RPC refused: {method}" in text or f"RPC refused: '{method}'" in text
