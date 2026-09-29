"""Exercise signed transfers, failed scripts, RPC bypasses, and chain capture."""
import argparse
import json
import os
import time
from dataclasses import replace
from pathlib import Path

from inspect_ai import eval
from inspect_ai.log import read_eval_log
from inspect_ai.solver import solver
from inspect_ai.util import sandbox

from ethevals.checks import check_player, check_grader
from support import load_config
from ethevals.loader import load_eval
from ethevals.preparation import prepare_compose, prepare_eval
from ethevals.runner import build_task
from ethevals.rows import export_rows
from ethevals.sandboxes import runner_exec


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
            await sandbox("chain").write_file("/eval/scorer/check.py", b"raise RuntimeError('crash proof')\n")
        elif variant == "missing":
            await sandbox("chain").write_file("/eval/scorer/check.py", b'print(\'{"recipient_balance":{"passed":false,"reason":"Missing sender proof."}}\')\n')
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
            probe = b"""import sys, time
sys.path.insert(0, '/opt')
from rpc_filter import rpc
before = rpc('eth_getBlockByNumber', ['latest', False])['hash']
assert rpc('txpool_content') == {'pending': {}, 'queued': {}}
time.sleep(4)
assert rpc('eth_getBlockByNumber', ['latest', False])['hash'] == before
"""
            await sandbox("chain").write_file("/eval/scorer/check.py", probe + original)
        return await generate(state)
    return solve


def run_proof(output, variants=None):
    assert not any(os.environ.get(name) for name in ("OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_AUTH_TOKEN"))
    config = load_config()
    root = Path(__file__).resolve().parents[2]
    evaluation = load_eval(root / "evals/transactions/send-six-decimal-token", config)
    compose = prepare_compose(evaluation, output)
    evaluation = prepare_eval(evaluation, output, compose)
    tasks = []
    variants = variants or ("reference", "wrong", "crash", "missing", "cheat", "pending")
    for variant in variants:
        player = check_player(evaluation, "empty")
        player = replace(player, metadata={**player.metadata, "epoch": list(variants).index(variant) + 1},
                         solver_for=lambda _, variant=variant: attempt(evaluation, variant))
        tasks.append(build_task(evaluation, config, player, check_grader(), "internet", 1, compose))
    started = time.monotonic()
    eval(tasks, log_dir=str(output / "logs"), display="plain", retry_on_error=0, fail_on_error=False, max_tasks=2)
    rows = export_rows(output)
    for row in rows:
        assert row["status"] == ("passed" if list(variants)[row["epoch"] - 1] == "reference" else "failed"), row
        assert set(row["checks"]) == {"script:agent_sender", "script:recipient_balance"}
        if list(variants)[row["epoch"] - 1] == "wrong":
            assert row["checks"]["script:recipient_balance"] == {"passed": False, "reason": "Recipient holds 13000000 base units; expected 12500000."}
        if list(variants)[row["epoch"] - 1] == "pending":
            assert row["checks"]["script:recipient_balance"] == {"passed": False, "reason": "Recipient holds 0 base units; expected 12500000."}
        if list(variants)[row["epoch"] - 1] == "cheat":
            log = read_eval_log(str(output / row["log_file"]))
            text = log.model_dump_json()
            for method in ("eth_sendTransaction", "eth_sendUnsignedTransaction", "anvil_setBalance", "HTTP GET"):
                assert f"RPC refused: {method}" in text or f"RPC refused: '{method}'" in text
    print(json.dumps({"seconds": round(time.monotonic() - started, 2), "rows": rows}), flush=True)
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--variant", action="append")
    args = parser.parse_args()
    run_proof(args.output, args.variant)
