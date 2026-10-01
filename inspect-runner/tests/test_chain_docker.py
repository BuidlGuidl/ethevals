from dataclasses import replace
import json
from pathlib import Path
import anyio

from ethevals.checks import check_agent, check_grader
from ethevals.loader import load_eval
from ethevals.preparation import build_images, prepare_compose
from ethevals.rows import results_rows
from ethevals.runner import build_task
from ethevals.sandboxes import runner_exec
from ethevals.scorers import TargetScorer
from inspect_ai import eval
from inspect_ai.solver import solver
from inspect_ai.util import sandbox
import pytest

from support import fixture_config


pytestmark = pytest.mark.docker
ROOT = Path(__file__).resolve().parents[2]


def run_probe(evaluation, tmp_path, probe=None, answer="empty"):
    build_images()
    config = fixture_config()
    agent = check_agent(evaluation, answer)
    if probe:
        agent = replace(agent, solver_for=lambda _: probe)
    task = build_task(evaluation, config, agent, check_grader(), "internet", 1,
                      prepare_compose(evaluation, tmp_path))
    log = eval(task, log_dir=str(tmp_path / "logs"), display="none", retry_on_error=0)[0]
    return log, results_rows(log)[0]


def test_agent_and_scorer_network_isolation(tmp_path):
    evaluation = load_eval(ROOT / "evals/transactions/send-six-decimal-token", fixture_config())
    observed = {}

    @solver
    def probe():
        async def solve(state, generate):
            for name in ("scorer", "chain"):
                result = await runner_exec(sandbox(), ["getent", "hosts", name])
                observed[name] = result.returncode
            result = await runner_exec(sandbox("scorer"), ["cast", "rpc", "--rpc-url", "http://chain:8545", "eth_chainId"])
            observed["rpc"] = (result.returncode, result.stdout.strip())
            return state
        return solve

    _, row = run_probe(evaluation, tmp_path, probe())
    assert observed == {"scorer": 2, "chain": 0, "rpc": (0, '"0x7a69"')}
    assert row["status"] == "failed", row


def test_slow_setup_preserves_agent_time(tmp_path):
    evaluation = load_eval(ROOT / "evals/transactions/send-six-decimal-token", fixture_config())
    files = {**evaluation.files, "setup/setup.s.sol": evaluation.files["setup/setup.s.sol"].replace(
        b'    function run() external {', b'    function run() external {\n        vm.sleep(31_000);')}
    # Keep grading below Inspect's separate 15-second scoring allowance.
    evaluation = replace(evaluation, files=files, scorer_kinds=["target"],
                         target=TargetScorer(name="reply", target="ready"))
    config = fixture_config()
    agent = check_agent(evaluation, "reference")

    @solver
    def slow_agent():
        async def solve(state, generate):
            await anyio.sleep(1)
            return await generate(state)
        return solve

    agent = replace(agent, solver_for=lambda _: slow_agent())
    build_images()
    task = build_task(evaluation, config, agent, check_grader(), "internet", 1, prepare_compose(evaluation, tmp_path))
    task.time_limit = 30
    log = eval(task, log_dir=str(tmp_path / "logs"), display="none", retry_on_error=0)[0]
    row = results_rows(log)[0]
    assert row["status"] == "passed", row
    assert row["checks"] == {"reply": {"passed": True, "reason": "Answer matches the target."}}
    assert row["total_tokens"] > 0
    assert not any(event.event == "sample_limit" for event in log.samples[0].events)


def test_setup_records_and_real_funding(tmp_path):
    evaluation = load_eval(ROOT / "evals/transactions/send-six-decimal-token", fixture_config())
    extra = b'''
        address funded = address(0x1234);
        address simulated = address(0x5678);
        vm.deal(simulated, 7 ether);
        fund(funded, 3 ether);
        chainRecord("funded", funded);
        chainRecord("amount", uint256(42));
        chainRecord("tag", bytes32(uint256(99)));
        chainRecord("note", string("hello"));
        privateRecord("funded", funded);
        privateRecord("simulated", simulated);
        privateRecord("amount", uint256(42));
        privateRecord("tag", bytes32(uint256(99)));
        privateRecord("note", string("hidden"));
'''
    files = {**evaluation.files, "setup/setup.s.sol": evaluation.files["setup/setup.s.sol"].replace(
        b'        chainRecord("token", address(token));', b'        chainRecord("token", address(token));' + extra)}
    files["scorer/tests/Funding.t.sol"] = b'''
pragma solidity 0.8.30;
import {Test} from "forge-std/Test.sol";
import {stdJson} from "forge-std/StdJson.sol";
contract FundingCheck is Test {
    using stdJson for string;
    function test_real_funding() public {
        string memory original = vm.readFile("chain.json");
        string memory secret = vm.readFile("private.json");
        vm.createSelectFork("chain");
        assertEq(original.readUint(".amount"), 42, "untouched chain file");
        assertEq(secret.readUint(".amount"), 42, "private uint");
        assertEq(secret.readString(".note"), "hidden", "private string");
        assertEq(secret.readBytes32(".tag"), bytes32(uint256(99)), "private bytes32");
        assertEq(secret.readAddress(".funded").balance, 3 ether, "fund changes Anvil");
        assertEq(secret.readAddress(".simulated").balance, 0, "deal stays in simulation");
    }
}
'''
    evaluation = replace(evaluation, files=files)
    observed = {}

    @solver
    def probe():
        async def solve(state, generate):
            public = await sandbox().read_file("/workspace/chain.json", text=False)
            original = await sandbox("scorer").read_file("/workspace/chain.json", text=False)
            observed["same"] = public == original
            observed["chain"] = json.loads(public)
            observed["private"] = json.loads(await sandbox("scorer").read_file("/workspace/private.json"))
            private = await runner_exec(sandbox(), ["test", "-e", "/workspace/private.json"])
            observed["private_absent"] = private.returncode
            await sandbox().write_file("/workspace/chain.json", '{"amount": 999}')
            return state
        return solve

    _, row = run_probe(evaluation, tmp_path, probe())
    assert observed["same"] is True
    assert {name: observed["chain"][name] for name in ("rpcUrl", "chainId", "funded", "amount", "tag", "note")} == {
        "rpcUrl": "http://chain:8545", "chainId": 31337, "funded": "0x0000000000000000000000000000000000001234",
        "amount": 42, "tag": "0x" + "0" * 62 + "63", "note": "hello"}
    assert observed["private"] == {"funded": "0x0000000000000000000000000000000000001234",
        "simulated": "0x0000000000000000000000000000000000005678", "amount": 42,
        "tag": "0x" + "0" * 62 + "63", "note": "hidden"}
    assert observed["private_absent"] == 1
    assert row["checks"]["test_real_funding"] == {"passed": True, "reason": "Test passed."}, row
    assert row["checks"]["test_recipient_balance"]["passed"] is False


TRANSFER = '''set -eu
read_value() { node -e "process.stdout.write(JSON.parse(require('fs').readFileSync('chain.json', 'utf8'))[process.argv[1]])" "$1"; }
token=$(read_value token)
recipient=$(read_value recipient)
key=$(read_value privateKey)
rpc=$(read_value rpcUrl)
decimals=$(cast call "$token" 'decimals()(uint8)' --rpc-url "$rpc")
amount=$((125 * 10 ** decimals / 10))
cast send "$token" 'transfer(address,uint256)' "$recipient" "$amount" --private-key "$key" --rpc-url "$rpc"
'''


@pytest.mark.parametrize("variant", ["reference", "wrong", "cheat", "pending"])
def test_transfers_and_grading_boundary(tmp_path, variant):
    evaluation = load_eval(ROOT / "evals/transactions/send-six-decimal-token", fixture_config())
    observed = {}
    files = dict(evaluation.files)
    files["scorer/tests/Transfer.t.sol"] = files["scorer/tests/Transfer.t.sol"].replace(
        b'        vm.createSelectFork("chain");',
        b'        vm.createSelectFork("chain");\n        assertGt(block.number, chain.readUint(".lastBlock"), "runner mined a block");')
    if variant == "pending":
        files["scorer/tests/Transfer.t.sol"] = files["scorer/tests/Transfer.t.sol"].replace(
            b'        vm.createSelectFork("chain");', b'        vm.sleep(4_000);\n        vm.createSelectFork("chain");')
    evaluation = replace(evaluation, files=files)

    @solver
    def attempt():
        async def solve(state, generate):
            box = sandbox()
            if variant in {"reference", "wrong", "pending"}:
                source = TRANSFER
                if variant == "wrong":
                    source = source.replace("125 * 10 ** decimals / 10", "13 * 10 ** decimals")
                if variant == "pending":
                    source = source.replace('cast send "$token"', 'cast send --async --nonce 1 "$token"')
                result = await runner_exec(box, ["/bin/bash", "-c", source], timeout=60)
                observed["send"] = (result.returncode, result.stderr)
                if variant == "pending":
                    await box.write_file("/workspace/transfer.sh", TRANSFER)
                    result = await runner_exec(box, ["/bin/bash", "-c",
                        "nohup bash -c 'sleep 3; bash /workspace/transfer.sh' >/tmp/writer.log 2>&1 </dev/null &"])
                    assert result.success, result.stderr
            elif variant == "cheat":
                result = await runner_exec(box, ["/bin/bash", "-c", r'''set -eu
for method in eth_sendTransaction eth_sendUnsignedTransaction anvil_setBalance; do
    curl -sS -H 'Content-Type: application/json' --data "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"$method\",\"params\":[]}" http://chain:8545
done
curl -sS -H 'Content-Type: application/json' --data '[{"jsonrpc":"2.0","id":1,"method":"eth_chainId"},{"jsonrpc":"2.0","id":2,"method":"eth_sendUnsignedTransaction","params":[]}]' http://chain:8545
curl -sS -H 'Connection: Upgrade' -H 'Upgrade: websocket' http://chain:8545
if curl -sS --connect-timeout 2 http://chain:8546; then exit 1; fi
'''])
                observed["cheat"] = (result.returncode, result.stdout)
            latest = await runner_exec(sandbox("chain"), ["cast", "block-number", "--rpc-url", "http://127.0.0.1:8546"])
            original = json.loads(await sandbox("scorer").read_file("/workspace/chain.json"))
            original["lastBlock"] = int(latest.stdout.strip())
            await sandbox("scorer").write_file("/workspace/chain.json", json.dumps(original))
            await box.write_file("/workspace/chain.json", '{"recipient": "0x0000000000000000000000000000000000000000"}')
            return await generate(state)
        return solve

    log, row = run_probe(evaluation, tmp_path, attempt())
    assert row["status"] == ("passed" if variant == "reference" else "failed"), row
    assert row["checks"]["compile"] == {"passed": True, "reason": "Compilation passed."}
    if variant == "cheat":
        assert observed["cheat"][0] == 0
        assert observed["cheat"][1].count("-32601") == 5
        assert "405" in observed["cheat"][1]
        text = log.model_dump_json()
        for method in ("eth_sendTransaction", "eth_sendUnsignedTransaction", "anvil_setBalance", "HTTP GET"):
            assert f"RPC refused: {method}" in text or f"RPC refused: '{method}'" in text
    else:
        assert observed["send"][0] == 0, observed
    balance = row["checks"]["test_recipient_balance"]
    if variant == "reference":
        assert balance == {"passed": True, "reason": "Test passed."}
    else:
        actual = 13000000 if variant == "wrong" else 0
        assert balance == {"passed": False,
            "reason": f"recipient holds 12.5 tokens in base units: {actual} != 12500000"}


@pytest.mark.parametrize("variant", ["collision", "lint"])
def test_setup_rejects_agent_visible_errors(tmp_path, variant):
    evaluation = load_eval(ROOT / "evals/transactions/send-six-decimal-token", fixture_config())
    files = dict(evaluation.files)
    if variant == "collision":
        files["workspace/chain.json"] = b'{"rpcUrl": "original"}'
    else:
        files["setup/setup.s.sol"] = files["setup/setup.s.sol"].replace(
            b'        chainRecord("token", address(token));',
            b'        chainRecord("token", address(token));\n        chainRecord("note", string("EVAL"));')
    _, row = run_probe(replace(evaluation, files=files), tmp_path, answer="reference")
    assert row["status"] == "error", row
    assert ("cannot replace workspace/chain.json" if variant == "collision" else "forbidden word 'EVAL'") in row["error_reason"]
