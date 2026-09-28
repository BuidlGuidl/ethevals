"""A bounded JSON-RPC allowlist and a local-only grading boundary."""
import argparse
import json
import os
import socket
import socketserver
import subprocess
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

READS = frozenset({
    "web3_clientVersion", "web3_sha3", "net_version", "net_listening", "net_peerCount",
    "eth_chainId", "eth_blockNumber", "eth_syncing", "eth_gasPrice", "eth_maxPriorityFeePerGas",
    "eth_feeHistory", "eth_getBalance", "eth_getTransactionCount", "eth_getCode", "eth_getStorageAt",
    "eth_call", "eth_estimateGas", "eth_getBlockByHash", "eth_getBlockByNumber",
    "eth_getBlockTransactionCountByHash", "eth_getBlockTransactionCountByNumber",
    "eth_getTransactionByHash", "eth_getTransactionByBlockHashAndIndex",
    "eth_getTransactionByBlockNumberAndIndex", "eth_getTransactionReceipt", "eth_getLogs", "eth_getProof",
    "eth_accounts", "eth_getAccountInfo",
})
ALLOWED = READS | {"eth_sendRawTransaction"}
MAX_BODY = 2 * 1024 * 1024
CONTROL = "/tmp/ethevals-chain.sock"
REFUSALS = "/tmp/rpc-refusals.log"
LOG_BYTES = 1048576
LOG_LOCK = threading.Lock()


def refusal(message):
    line = (f"RPC refused: {message}".encode("utf-8")[:1023] + b"\n")
    # Keep one bounded sink. Docker stdout has no total-size limit.
    with LOG_LOCK, open(REFUSALS, "ab") as log:
        remaining = max(0, LOG_BYTES - log.tell())
        log.write(line[:remaining])


def rpc(method, params=None):
    data = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params or []}).encode()
    request = urllib.request.Request("http://127.0.0.1:8546", data, {"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=15) as response:
        result = json.load(response)
    if "error" in result:
        raise RuntimeError(result["error"])
    return result["result"]


def error(request, code, message):
    return {"jsonrpc": "2.0", "id": request.get("id") if isinstance(request, dict) else None,
            "error": {"code": code, "message": message}}


class Chain:
    def __init__(self):
        self.lock = threading.Lock()
        self.frozen = False

    def forward(self, payload):
        batch = isinstance(payload, list)
        requests = payload if batch else [payload]
        if not requests or len(requests) > 100:
            return error(None, -32600, "Batch must contain 1 to 100 requests.")
        refused = []
        for request in requests:
            valid = (isinstance(request, dict) and request.get("jsonrpc") == "2.0" and
                     isinstance(request.get("method"), str) and
                     type(request.get("id")) in {str, int, type(None)} and
                     isinstance(request.get("params", []), (list, dict)))
            if not valid or request["method"] not in ALLOWED:
                method = request.get("method") if isinstance(request, dict) else None
                refusal(repr(method))
                refused.append(error(request, -32601 if valid else -32600,
                                     "Method is not allowed." if valid else "Invalid JSON-RPC request."))
        # Reject the whole batch before forwarding any member.
        if refused:
            return [error(request, -32601, "Batch contains a refused method.") for request in requests] if batch else refused[0]
        with self.lock:
            if self.frozen:
                return error(None, -32000, "Chain is closed for grading.")
            data = json.dumps(payload).encode()
            request = urllib.request.Request("http://127.0.0.1:8546", data, {"Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=15) as response:
                body = response.read(MAX_BODY + 1)
                if len(body) > MAX_BODY:
                    return error(None, -32000, "Chain response too large.")
                return json.loads(body)

    def freeze(self):
        # Reject waiting requests before taking the lock held by the current request.
        self.frozen = True
        with self.lock:
            rpc("anvil_setIntervalMining", [0])
            rpc("evm_setAutomine", [False])
            pool = rpc("txpool_content")
            # dropTransaction leaves future-nonce transactions in Anvil 1.5.1's pool.
            for address in {address for section in pool.values() for address in section}:
                rpc("anvil_removePoolTransactions", [address])
            if any(rpc("txpool_content").values()):
                raise RuntimeError("Transaction pool did not empty at the grading boundary.")
            # Anvil's awaited manual mine takes the same mining mutex as automine.
            # With the pool empty, this seals an empty block after active mining.
            rpc("evm_mine")
            return rpc("eth_getBlockByNumber", ["latest", False])["hash"]


class Handler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def reject(self, status, message):
        refusal(f"HTTP {self.command} {message}")
        self.send_error(status, message)

    def do_GET(self):
        self.reject(405, "Only JSON-RPC POST is allowed.")

    def do_POST(self):
        self.close_connection = True
        if self.path != "/" or self.headers.get("Upgrade") or self.headers.get("Transfer-Encoding"):
            return self.reject(400, "Path, upgrade, or transfer encoding is not allowed.")
        if self.headers.get_content_type() != "application/json":
            return self.reject(415, "Content-Type must be application/json.")
        try:
            lengths = self.headers.get_all("Content-Length", [])
            size = int(lengths[0]) if len(lengths) == 1 else -1
            if not 0 < size <= MAX_BODY:
                return self.reject(413, "Invalid request length.")
            payload = json.loads(self.rfile.read(size))
            response = self.server.chain.forward(payload)
        except (ValueError, UnicodeError):
            response = error(None, -32700, "Invalid JSON.")
        except Exception:
            response = error(None, -32000, "Chain request failed.")
        data = json.dumps(response).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, chain):
        super().__init__(address, Handler)
        self.chain = chain
        self.slots = threading.BoundedSemaphore(32)

    def process_request(self, request, address):
        if not self.slots.acquire(blocking=False):
            request.close()
            return
        super().process_request(request, address)

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self.slots.release()

    def handle_error(self, request, address):
        # Disconnected clients cannot produce unlimited traceback output.
        refusal("HTTP connection failed.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze", action="store_true")
    args = parser.parse_args()
    if args.freeze:
        with socket.socket(socket.AF_UNIX) as client:
            client.settimeout(45)
            client.connect(CONTROL)
            client.sendall(b"freeze\n")
            with client.makefile("rb") as response:
                result = json.loads(response.read(4097))
            if "error" in result:
                raise RuntimeError(result["error"])
            print(json.dumps(result))
        return
    process = subprocess.Popen(["anvil", "--host", "127.0.0.1", "--port", "8546", "--accounts", "0", "--silent"])
    open(REFUSALS, "w").close()
    for attempt in range(100):
        try:
            rpc("eth_chainId")
            break
        except Exception:
            if process.poll() is not None:
                raise RuntimeError("Anvil exited during startup.")
            time.sleep(0.1)
    else:
        raise RuntimeError("Anvil did not start.")
    chain = Chain()

    class Control(socketserver.StreamRequestHandler):
        def handle(self):
            self.connection.settimeout(45)
            try:
                if self.rfile.readline(32) != b"freeze\n":
                    raise ValueError("Unknown control request")
                result = {"block_hash": chain.freeze()}
            except Exception as exc:
                result = {"error": str(exc)}
            self.wfile.write(json.dumps(result).encode())

    if os.path.exists(CONTROL):
        os.unlink(CONTROL)
    control = socketserver.UnixStreamServer(CONTROL, Control)
    os.chmod(CONTROL, 0o600)
    threading.Thread(target=control.serve_forever, daemon=True).start()
    Server(("0.0.0.0", 8545), chain).serve_forever()


if __name__ == "__main__":
    main()
