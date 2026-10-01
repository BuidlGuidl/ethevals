from dataclasses import replace
import json
from pathlib import Path
import subprocess
import time
import uuid

import pytest
from inspect_ai.solver import solver
from inspect_ai.model import ChatMessageAssistant, execute_tools
from inspect_ai.tool import bash, ToolCall
from inspect_ai.log import read_eval_log
from inspect_ai.util import sandbox

from ethevals import preparation
from ethevals.images.tag import image_tag
from ethevals.loader import ForkChain, load_eval
from ethevals.sandboxes import IMAGES, runner_exec
from ethevals.rows import write_rows
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
        monkeypatch.setenv("MAINNET_RPC_URL", "http://upstream:8545?key=SENTINEL")
        yield name
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
    files["scorer/tests/Transfer.t.sol"] = files["scorer/tests/Transfer.t.sol"].replace(
        b'    function test_recipient_balance()',
        b'    function test_uncached_balance() public view {\n'
        b'        assertEq(address(0xDEAD).balance, 0, "uncached balance");\n'
        b'    }\n\n    function test_recipient_balance()')
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
            info = await runner_exec(sandbox("chain"), ["cast", "rpc", "--rpc-url", "http://127.0.0.1:8546", "anvil_nodeInfo"])
            observed["node_info"] = info.stdout
            docker("stop", local_upstream)
            command = """curl -sS -H 'Content-Type: application/json' --data '{"jsonrpc":"2.0","id":17,"method":"eth_getBalance","params":["0x000000000000000000000000000000000000cafe","latest"]}' http://chain:8545 | tee fork-error.json"""
            state.tools = [bash(timeout=90)]
            state.messages.append(ChatMessageAssistant(content="", tool_calls=[
                ToolCall(id="fork-read", function="bash", arguments={"command": command})]))
            results = await execute_tools(state.messages, state.tools)
            state.messages.extend(results.messages)
            observed["tool_output"] = results.messages[0].text
            observed["response_file"] = await sandbox().read_file("/workspace/fork-error.json")
            direct = await runner_exec(sandbox("chain"), ["cast", "rpc", "--rpc-url", "http://127.0.0.1:8546",
                "eth_getBalance", "0x000000000000000000000000000000000000babe", "latest"])
            observed["direct"] = (direct.returncode, direct.stdout, direct.stderr)
            return state
        return solve

    log, row = run_probe(evaluation, tmp_path, transfer())
    assert row["status"] == "error", row
    assert observed["chain"]["rpcUrl"] == "http://chain:8545"
    assert observed["chain"]["chainId"] == 8453
    assert observed["chain"]["upstreamBalance"] == 7 * 10**18
    assert observed["sent"][0] == 0, observed
    assert observed["refused"] == {"jsonrpc": "2.0", "id": 1, "error": {
        "code": -32601, "message": "Sign locally and use eth_sendRawTransaction."}}
    assert "error sending request for url (<fork rpc>)" in row["error_reason"]
    response = json.loads(observed["tool_output"])
    assert response["id"] == 17
    assert response["error"]["code"] == -32603
    assert "<fork rpc>" in response["error"]["message"]
    assert observed["response_file"] == observed["tool_output"]
    assert "<fork rpc>" in observed["node_info"]
    assert observed["direct"][0] == 1
    assert "<fork rpc>" in observed["direct"][2]
    write_rows(tmp_path / "rows.jsonl", [row])
    decoded = [read_eval_log(path).model_dump_json() for path in (tmp_path / "logs").glob("*.eval")]
    assert len(decoded) == 1
    captured = json.dumps(observed) + json.dumps(row) + log.model_dump_json() + "".join(decoded)
    for value in ("http://upstream:8545", "SENTINEL"):
        assert value not in captured
    saved = [file.read_bytes() for file in tmp_path.rglob("*") if file.is_file()]
    assert saved
    assert all(b"http://upstream:8545" not in content for content in saved)
    assert all(b"SENTINEL" not in content for content in saved)
    print("Agent error:", observed["tool_output"])
    print("Unfiltered command error:", observed["direct"][2].strip())
    print("Row error:", row["error_reason"].split("error sending request for url", 1)[1].split("\\n", 1)[0])
    print("No fork URL or sentinel in agent output, rows, saved files, or decoded logs.")
