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

    request.chain = server.chain
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
                                    "eth_estimateGas", "eth_feeHistory", "eth_getTransactionReceipt", "eth_getCode",
                                    "eth_accounts", "eth_getAccountInfo"])
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


def test_frozen_proxy_refuses_without_forwarding(proxy, monkeypatch):
    request, writes = proxy
    monkeypatch.setattr(rpc_filter, "rpc", lambda method, params=None:
                        {"hash": "0xsealed"} if method == "eth_getBlockByNumber" else {})
    payload = {"jsonrpc": "2.0", "id": 1, "method": "eth_sendRawTransaction", "params": ["0x123"]}
    assert json.loads(request(payload)[1])["result"] == "0xabc"
    assert request.chain.freeze() == "0xsealed"
    assert json.loads(request(payload)[1]) == {
        "jsonrpc": "2.0", "id": None, "error": {"code": -32000, "message": "Chain is closed for grading."}}
    assert writes == [payload]


def test_freeze_waits_for_active_request(proxy, monkeypatch):
    request, writes = proxy
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    upstream = rpc_filter.urllib.request.urlopen

    def slow(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return upstream(*args, **kwargs)

    monkeypatch.setattr(rpc_filter.urllib.request, "urlopen", slow)
    monkeypatch.setattr(rpc_filter, "rpc", lambda method, params=None:
                        {"hash": "0xsealed"} if method == "eth_getBlockByNumber" else {})
    payload = {"jsonrpc": "2.0", "id": 1, "method": "eth_chainId"}
    replies, captures = [], []
    sender = threading.Thread(target=lambda: replies.append(request(payload)))

    def freeze():
        captures.append(request.chain.freeze())
        finished.set()

    sender.start()
    assert entered.wait(5)
    closer = threading.Thread(target=freeze)
    closer.start()
    try:
        assert not finished.wait(.1)
    finally:
        release.set()
        sender.join(5)
        closer.join(5)
    assert json.loads(replies[0][1])["result"] == "0xabc"
    assert captures == ["0xsealed"]
    assert writes == [payload]


def test_refused_large_methods_have_bounded_output(tmp_path, monkeypatch, capsys):
    log = tmp_path / "refusals.log"
    monkeypatch.setattr(rpc_filter, "REFUSALS", log)
    chain = rpc_filter.Chain()
    for _ in range(5):
        result = chain.forward({"jsonrpc": "2.0", "id": 1, "method": "x" * 2_000_000})
        assert result["error"]["message"] == "Method is not allowed."
    assert log.stat().st_size == 5120
    for _ in range(1100):
        rpc_filter.refusal("x" * 2000)
    assert log.stat().st_size == 1048576
    assert capsys.readouterr().out == ""


def test_oversized_upstream_response_has_accurate_error(proxy, monkeypatch):
    request, writes = proxy
    monkeypatch.setattr(rpc_filter, "MAX_BODY", 100)
    import io
    monkeypatch.setattr(rpc_filter.urllib.request, "urlopen", lambda *args, **kwargs: io.BytesIO(b"x" * 101))
    status, body = request({"jsonrpc": "2.0", "id": 1, "method": "eth_chainId"})
    assert status == 200
    assert json.loads(body)["error"] == {"code": -32000, "message": "Chain response too large."}


@pytest.mark.parametrize("output", [None, [], {}, {"files": [],}, {"files": {}, "extra": 1},
    {"files": {"/absolute": "x"}}, {"files": {"../parent": "x"}}, {"files": {"a/../b": "x"}},
    {"files": {"a//b": "x"}}, {"files": {".": "x"}}, {"files": {"": "x"}},
    {"files": {"value": 1}}, {"files": {3: "x"}}, {"files": {"README.md": "replacement"}}])
def test_setup_rejects_invalid_output(output):
    from ethevals.check_script import setup_files
    with pytest.raises(ValueError, match="setup.py"):
        setup_files(output, {"workspace/README.md": b"original"})


def test_setup_accepts_selected_nested_files():
    from ethevals.check_script import setup_files
    assert setup_files({"files": {"data/key.json": "key", "chain.json": "chain"}}, {}) == {
        "data/key.json": "key", "chain.json": "chain"}


@pytest.mark.parametrize("value", [None, [], {}, {"Bad": {"passed": True, "reason": "yes"}},
    {1: {"passed": True, "reason": "yes"}}, {"ok": None}, {"ok": {"passed": 1, "reason": "yes"}},
    {"ok": {"passed": True, "reason": " "}}, {"ok": {"passed": True, "reason": 1}},
    {"ok": {"passed": True}}, {"ok": {"passed": True, "reason": "yes", "extra": 1}}])
def test_check_script_rejects_invalid_checks(value):
    from ethevals.check_script import script_checks
    with pytest.raises(ValueError, match="check.py"):
        script_checks(value)


def test_check_script_normalizes_reasons():
    from ethevals.check_script import script_checks
    assert script_checks({"balance": {"passed": False, "reason": " Balance\n is zero. "}}) == {
        "script:balance": {"passed": False, "reason": "Balance is zero."}}


def test_act_requires_check_script_and_allows_declared_chain_file(tmp_path):
    import shutil
    root = Path(__file__).resolve().parents[2]
    folder = tmp_path / "transactions" / "act"
    shutil.copytree(root / "evals/transactions/send-six-decimal-token", folder)
    (folder / "workspace/chain.json").write_text("declared input")
    assert load_eval(folder, load_config()).files["workspace/chain.json"] == b"declared input"
    (folder / "scorer/scorer.yaml").write_text("scorers:\n  - kind: tests\n")
    (folder / "scorer/tests").mkdir()
    (folder / "scorer/tests/Test.t.sol").write_text("contract Test {}")
    with pytest.raises(ValueError, match="act evals require check_script"):
        load_eval(folder, load_config())


def test_compose_rejects_private_network_with_host_gateway(tmp_path):
    import yaml
    data = yaml.safe_load(compose_file("act").read_bytes())
    del data["networks"]["private"]["driver_opts"]
    with pytest.raises(ValueError, match="inhibit_ipv4"):
        validate_compose(tmp_path / "compose.yaml", stock=True, data=yaml.safe_dump(data).encode())


def test_script_failure_includes_stderr_tail():
    import anyio
    from inspect_ai.util import ExecResult
    from ethevals.check_script import script_result
    from ethevals.scoring_base import SubmissionFailed

    class Box:
        async def exec(self, command, **kwargs):
            if "/usr/bin/test" in command or "/sys/fs/cgroup/memory.events" in command:
                return ExecResult(success=True, returncode=0, stdout="oom 0\noom_kill 0\n", stderr="")
            return ExecResult(success=False, returncode=1, stdout="", stderr="")

        async def read_file(self, path, **kwargs):
            if path.endswith("status"):
                return "1"
            return b"" if path.endswith("stdout") else b"x" * 6000 + b"\nValueError: bad setup amount"

    with pytest.raises(SubmissionFailed, match="ValueError: bad setup amount") as error:
        anyio.run(script_result, "setup", Box())
    assert len(str(error.value)) < 4200


def test_failed_reference_discovery_names_checks(tmp_path, monkeypatch):
    from dataclasses import replace
    from inspect_ai import Task, eval
    from inspect_ai.model import get_model
    from ethevals.preparation import reference_checks, no_player
    from ethevals.scorers import SCORERS, EVALUATIONS

    evaluation = load_eval(Path(__file__).resolve().parents[2] / "evals/transactions/send-six-decimal-token", load_config())
    EVALUATIONS[(evaluation.id, evaluation.hash)] = evaluation

    async def discover(*args):
        return {"script:balance": {"passed": False, "reason": "Recipient holds zero."}}

    monkeypatch.setitem(SCORERS, "check_script", replace(SCORERS["check_script"], discover=discover))
    sample = evaluation.sample()
    sample.files = None
    task = Task(dataset=[sample], solver=no_player(), model=get_model("mockllm/model"),
                scorer=reference_checks(evaluation.id, evaluation.hash))
    log = eval(task, log_dir=str(tmp_path / "logs"), display="none", retry_on_error=0)[0]
    assert "script:balance: Recipient holds zero." in log.samples[0].error.message


def test_docker_build_error_is_local_to_eval_and_keeps_diagnostics(tmp_path, monkeypatch):
    import subprocess
    from ethevals.checks import check_player, check_grader
    from ethevals.runner import run
    import ethevals.preparation as preparation

    root = Path(__file__).resolve().parents[2]
    config = load_config()
    act = load_eval(root / "evals/transactions/send-six-decimal-token", config)
    quiz = load_eval(root / "evals/concepts/wei-per-ether", config)
    original = subprocess.run

    def command(args, **kwargs):
        if args[:2] == ["docker", "compose"] and "build" in args:
            raise subprocess.CalledProcessError(1, args, stderr="Docker: compiler checksum mismatch")
        return original(args, **kwargs)

    monkeypatch.setattr(preparation.subprocess, "run", command)
    success, rows = run([act, quiz], config, tmp_path,
                        answer="reference", epochs=1)
    assert success is False
    assert [(row["eval_id"], row["status"]) for row in rows] == [("concepts/wei-per-ether", "passed")]
    assert json.loads((tmp_path / "discovery-errors.json").read_text()) == [{
        "eval_id": act.id, "eval_hash": act.hash, "error": "Docker failed: Docker: compiler checksum mismatch"}]


def test_control_reads_fragmented_reply_to_eof(tmp_path, monkeypatch, capsys):
    import socket
    import sys
    import time
    monkeypatch.chdir(tmp_path)
    path = "control.sock"
    server = socket.socket(socket.AF_UNIX)
    server.bind(path)
    server.listen(1)
    monkeypatch.setattr(rpc_filter, "CONTROL", path)
    monkeypatch.setattr(sys, "argv", ["rpc_filter.py", "--freeze"])

    def reply():
        with server.accept()[0] as client:
            assert client.recv(32) == b"freeze\n"
            client.sendall(b'{"block_hash":')
            time.sleep(.05)
            client.sendall(b'"0xsealed"}')

    thread = threading.Thread(target=reply)
    thread.start()
    try:
        rpc_filter.main()
        assert json.loads(capsys.readouterr().out) == {"block_hash": "0xsealed"}
    finally:
        thread.join(5)
        server.close()
