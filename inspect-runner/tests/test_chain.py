import http.client
import threading
import json

from ethevals.images import rpc_filter
import pytest


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

    request.chain = server.chain
    yield request, writes
    server.shutdown()
    server.server_close()
    thread.join()


@pytest.mark.parametrize("method", [
    "hardhat_setBalance", "anvil_setBalance", "evm_setAccountNonce", "tenderly_setBalance",
    "debug_traceTransaction", "trace_transaction", "ots_getApiLevel", "txpool_content",
    "net_peerCount", "eth_unknownMethod",
])
def test_filter_refuses_controls_and_unknown_methods(proxy, method):
    request, writes = proxy
    status, body = request({"jsonrpc": "2.0", "id": 7, "method": method, "params": []})
    assert status == 200
    assert json.loads(body) == {"jsonrpc": "2.0", "id": 7, "error": {"code": -32601, "message": "Method is not allowed."}}
    _, allowed = request({"jsonrpc": "2.0", "id": 1, "method": "eth_chainId"})
    assert json.loads(allowed)["result"] == "0xabc"
    assert writes == [{"jsonrpc": "2.0", "id": 1, "method": "eth_chainId"}]


@pytest.mark.parametrize("method", [
    "eth_sendTransaction", "eth_sendTransactionSync", "eth_sendUnsignedTransaction",
    "eth_sign", "eth_signTransaction", "eth_signTypedData", "eth_signTypedData_v3",
    "eth_signTypedData_v4", "personal_sign",
])
def test_filter_refuses_node_signing_with_local_signing_advice(proxy, method):
    request, writes = proxy
    status, body = request({"jsonrpc": "2.0", "id": 7, "method": method, "params": []})
    assert (status, json.loads(body)) == (200, {"jsonrpc": "2.0", "id": 7, "error": {
        "code": -32601, "message": "Sign locally and use eth_sendRawTransaction."}})
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


@pytest.mark.parametrize("method", [
    "eth_sendRawTransaction", "eth_getBalance", "eth_newFilter", "eth_newBlockFilter",
    "eth_newPendingTransactionFilter", "eth_getFilterChanges", "eth_getFilterLogs",
    "eth_uninstallFilter", "eth_blobBaseFee", "eth_createAccessList", "eth_getBlockReceipts",
    "eth_simulateV1", "eth_sendRawTransactionSync", "eth_config",
])
def test_filter_passes_signed_sends_and_wallet_reads(proxy, method):
    request, writes = proxy
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": ["0x123"]}
    status, body = request(payload)
    assert (status, json.loads(body)["result"]) == (200, "0xabc")
    assert writes == [payload]


@pytest.mark.parametrize("method,code,message", [
    ("eth_sign", -32601, "Sign locally and use eth_sendRawTransaction."),
    ([], -32600, "Invalid JSON-RPC request."),
])
def test_filter_rejects_signing_and_malformed_batches(proxy, method, code, message):
    request, writes = proxy
    status, body = request([
        {"jsonrpc": "2.0", "id": 1, "method": "eth_sendRawTransaction", "params": ["0x123"]},
        {"jsonrpc": "2.0", "id": 2, "method": method},
    ])
    assert (status, json.loads(body)) == (200, [
        {"jsonrpc": "2.0", "id": 1, "error": {"code": -32601, "message": "Batch contains a refused method."}},
        {"jsonrpc": "2.0", "id": 2, "error": {"code": code, "message": message}},
    ])
    _, allowed = request({"jsonrpc": "2.0", "id": 3, "method": "eth_chainId"})
    assert json.loads(allowed)["result"] == "0xabc"
    assert writes == [{"jsonrpc": "2.0", "id": 3, "method": "eth_chainId"}]


def test_filter_rejects_websocket_beacon_and_non_json(proxy):
    request, writes = proxy
    assert request(method="GET", headers={"Connection": "Upgrade", "Upgrade": "websocket"})[0] == 405
    assert request(method="GET", path="/eth/v1/beacon/genesis")[0] == 405
    assert request({}, headers={"Content-Type": "text/plain"})[0] == 415
    assert request({}, headers={"Content-Type": "application/json", "Upgrade": "websocket"})[0] == 400
    assert request({}, path="/admin")[0] == 400
    request({"jsonrpc": "2.0", "id": 1, "method": "eth_chainId"})
    assert writes == [{"jsonrpc": "2.0", "id": 1, "method": "eth_chainId"}]


def test_filter_redacts_fork_urls_in_single_and_batch_responses(proxy, monkeypatch):
    request, _ = proxy
    request.chain.fork_url = "https://archive.example?key=SENTINEL"

    class Backend:
        def __init__(self, payload):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, size):
            response = {"jsonrpc": "2.0", "id": 1, "error": {"code": -32603, "message":
                "request https://archive.example?key=SENTINEL or https://archive.example/?key=SENTINEL failed"}}
            return json.dumps([response] if isinstance(self.payload, list) else response).encode()

    monkeypatch.setattr(rpc_filter.urllib.request, "urlopen",
                        lambda upstream, timeout: Backend(json.loads(upstream.data)))
    payload = {"jsonrpc": "2.0", "id": 1, "method": "eth_chainId"}
    expected = {"jsonrpc": "2.0", "id": 1, "error": {
        "code": -32603, "message": "request <fork rpc> or <fork rpc> failed"}}
    for batch in (False, True):
        status, body = request([payload] if batch else payload)
        assert status == 200
        assert json.loads(body) == ([expected] if batch else expected)
