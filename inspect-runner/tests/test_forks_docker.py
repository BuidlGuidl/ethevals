from dataclasses import replace
import json
from pathlib import Path
import subprocess
import time
import uuid

import pytest
from inspect_ai.solver import solver
from inspect_ai.util import sandbox

from ethevals import preparation
from ethevals.images.tag import image_tag
from ethevals.loader import ForkChain, load_eval
from ethevals.sandboxes import IMAGES, runner_exec
from support import fixture_config
from test_chain_docker import TRANSFER, run_probe


pytestmark = pytest.mark.docker
ROOT = Path(__file__).resolve().parents[2]


def docker(*args):
    return subprocess.run(["docker", *args], check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def local_upstream(monkeypatch):
    preparation.build_images()
    name = "fork-upstream-" + uuid.uuid4().hex[:12]
    docker("network", "create", name)
    try:
        docker("run", "-d", "--name", name, "--network", name, "--network-alias", "upstream",
               "--entrypoint", "anvil", image_tag(IMAGES, "chain"),
               "--host", "0.0.0.0", "--port", "8545", "--chain-id", "8453", "--accounts", "0", "--silent")
        for _ in range(30):
            try:
                docker("exec", name, "cast", "chain-id")
                break
            except subprocess.CalledProcessError:
                time.sleep(0.1)
        docker("exec", name, "cast", "rpc", "anvil_setBalance",
               "0x0000000000000000000000000000000000001234", "0x6124fee993bc0000")
        docker("exec", name, "cast", "rpc", "evm_mine")
        original = preparation.merged_compose

        def connect_upstream(evaluation):
            document = original(evaluation)
            document["networks"]["chain_internet"] = {"external": True, "name": name}
            return document

        monkeypatch.setattr(preparation, "merged_compose", connect_upstream)
        monkeypatch.setenv("MAINNET_RPC_URL", "http://upstream:8545")
        yield
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)
        docker("network", "rm", name)


def test_pinned_fork_reads_upstream_and_grades_the_filtered_transaction(tmp_path, local_upstream):
    evaluation = load_eval(ROOT / "evals/transactions/send-six-decimal-token", fixture_config())
    declaration = evaluation.declaration.model_copy(update={"chain": ForkChain(fork="mainnet", block=1)})
    files = dict(evaluation.files)
    files["setup/setup.s.sol"] = files["setup/setup.s.sol"].replace(
        b'        chainRecord("token", address(token));',
        b'        chainRecord("token", address(token));\n'
        b'        chainRecord("upstreamBalance", address(0x1234).balance);\n'
        b'        fund(address(0x5678), 2 ether);\n'
        b'        vm.rpc("anvil_impersonateAccount", \'["0x0000000000000000000000000000000000005678"]\');\n'
        b'        vm.rpc("eth_sendTransaction", \'[{"from":"0x0000000000000000000000000000000000005678",'
        b'"to":"0x0000000000000000000000000000000000009abc","value":"0xde0b6b3a7640000"}]\');\n'
        b'        vm.rpc("anvil_stopImpersonatingAccount", \'["0x0000000000000000000000000000000000005678"]\');')
    files["scorer/tests/Transfer.t.sol"] = files["scorer/tests/Transfer.t.sol"].replace(
        b'        vm.createSelectFork("chain");',
        b'        vm.createSelectFork("chain");\n'
        b'        assertEq(address(0x1234).balance, 7 ether, "upstream state survives");\n'
        b'        assertEq(address(0x9ABC).balance, 1 ether, "holder funding landed");\n'
        b'        assertGt(block.number, chain.readUint(".lastBlock"), "runner mined a block");')
    evaluation = replace(evaluation, declaration=declaration, files=files)
    observed = {}

    @solver
    def transfer():
        async def solve(state, generate):
            observed["chain"] = json.loads(await sandbox().read_file("/workspace/chain.json"))
            unsigned = json.dumps({"from": "0x0000000000000000000000000000000000005678",
                                   "to": "0x0000000000000000000000000000000000009abc", "value": "0x0"})
            payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "eth_sendTransaction",
                                  "params": [json.loads(unsigned)]})
            refused = await runner_exec(sandbox(), ["curl", "-sS", "-H", "Content-Type: application/json",
                                                   "--data", payload, "http://chain:8545"])
            observed["refused"] = json.loads(refused.stdout)
            result = await runner_exec(sandbox(), ["/bin/bash", "-c", TRANSFER], timeout=60)
            observed["sent"] = (result.returncode, result.stderr)
            latest = await runner_exec(sandbox("chain"), ["cast", "block-number", "--rpc-url", "http://127.0.0.1:8546"])
            chain = json.loads(await sandbox("scorer").read_file("/workspace/chain.json"))
            chain["lastBlock"] = int(latest.stdout.strip())
            await sandbox("scorer").write_file("/workspace/chain.json", json.dumps(chain))
            return state
        return solve

    log, row = run_probe(evaluation, tmp_path, transfer())
    assert row["status"] == "passed", row
    assert observed["chain"]["rpcUrl"] == "http://chain:8545"
    assert observed["chain"]["chainId"] == 8453
    assert observed["chain"]["upstreamBalance"] == 7 * 10**18
    assert observed["sent"][0] == 0, observed
    assert observed["refused"] == {"jsonrpc": "2.0", "id": 1, "error": {
        "code": -32601, "message": "Sign locally and use eth_sendRawTransaction."}}
    assert row["checks"] == {
        "compile": {"passed": True, "reason": "Compilation passed."},
        "test_recipient_balance": {"passed": True, "reason": "Test passed."}}
    assert "http://upstream:8545" not in log.model_dump_json()
    saved = [file.read_bytes() for file in tmp_path.rglob("*") if file.is_file()]
    assert saved
    assert all(b"http://upstream:8545" not in content for content in saved)
