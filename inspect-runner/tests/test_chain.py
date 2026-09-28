import http.client
import json
import threading
from pathlib import Path

import pytest

from ethevals.images import rpc_filter
from ethevals.loader import load_eval
from ethevals.config import load_config
from ethevals.sandboxes import compose_file, validate_compose


@pytest.fixture
def proxy(monkeypatch):
    writes = []

    class Backend:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, size):
            return b'{"jsonrpc":"2.0","id":1,"result":"0xabc"}'

    def upstream(request, timeout):
        writes.append(json.loads(request.data))
        return Backend()

    monkeypatch.setattr(rpc_filter.urllib.request, "urlopen", upstream)
    monkeypatch.setattr(rpc_filter, "refusal", lambda message: None)
    server = rpc_filter.Server(("127.0.0.1", 0), rpc_filter.Chain())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def request(payload=None, method="POST", headers=None, path="/"):
        connection = http.client.HTTPConnection(*server.server_address, timeout=5)
        data = json.dumps(payload) if payload is not None else None
        connection.request(method, path, data, headers or {"Content-Type": "application/json"})
        response = connection.getresponse()
        body = response.read()
        connection.close()
        return response.status, body

    yield request, writes
    server.shutdown()
    server.server_close()
    thread.join()


@pytest.mark.parametrize("method", ["eth_sendTransaction", "eth_sendUnsignedTransaction", "anvil_setBalance",
                                    "eth_sign", "personal_sign", "hardhat_setBalance", "evm_mine"])
def test_filter_refuses_keyless_sends_and_controls(proxy, method):
    request, writes = proxy
    status, body = request({"jsonrpc": "2.0", "id": 7, "method": method, "params": []})
    assert status == 200
    assert json.loads(body) == {"jsonrpc": "2.0", "id": 7, "error": {"code": -32601, "message": "Method is not allowed."}}
    _, allowed = request({"jsonrpc": "2.0", "id": 1, "method": "eth_chainId"})
    assert json.loads(allowed)["result"] == "0xabc"
    assert writes == [{"jsonrpc": "2.0", "id": 1, "method": "eth_chainId"}]


def test_filter_rejects_entire_mixed_batch(proxy):
    request, writes = proxy
    status, body = request([{"jsonrpc": "2.0", "id": 1, "method": "eth_sendRawTransaction", "params": ["0x123"]},
                            {"jsonrpc": "2.0", "id": 2, "method": "anvil_setBalance", "params": []}])
    assert status == 200
    assert [item["error"]["code"] for item in json.loads(body)] == [-32601, -32601]
    request({"jsonrpc": "2.0", "id": 3, "method": "eth_getBalance", "params": ["0x123", "latest"]})
    assert writes == [{"jsonrpc": "2.0", "id": 3, "method": "eth_getBalance", "params": ["0x123", "latest"]}]


@pytest.mark.parametrize("method", ["eth_sendRawTransaction", "eth_chainId", "eth_getTransactionCount", "eth_call",
                                    "eth_estimateGas", "eth_feeHistory", "eth_getTransactionReceipt", "eth_getCode"])
def test_filter_passes_signed_sends_and_wallet_reads(proxy, method):
    request, writes = proxy
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": ["0x123"]}
    status, body = request(payload)
    assert (status, json.loads(body)["result"]) == (200, "0xabc")
    assert writes == [payload]


def test_filter_rejects_websocket_beacon_and_non_json(proxy):
    request, writes = proxy
    assert request(method="GET", headers={"Connection": "Upgrade", "Upgrade": "websocket"})[0] == 405
    assert request(method="GET", path="/eth/v1/beacon/genesis")[0] == 405
    assert request({}, headers={"Content-Type": "text/plain"})[0] == 415
    assert request({}, headers={"Content-Type": "application/json", "Upgrade": "websocket"})[0] == 400
    assert request({}, path="/admin")[0] == 400
    request({"jsonrpc": "2.0", "id": 1, "method": "eth_chainId"})
    assert writes == [{"jsonrpc": "2.0", "id": 1, "method": "eth_chainId"}]


def test_act_stock_compose_and_sample():
    root = Path(__file__).resolve().parents[2]
    evaluation = load_eval(root / "evals/transactions/send-six-decimal-token", load_config())
    sample = evaluation.sample()
    assert set(sample.files) == {"/workspace/README.md"}
    assert "12.5 tokens" in sample.input
    assert b"internal: true" in validate_compose(compose_file("act"), stock=True)
