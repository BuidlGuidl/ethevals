"""Forward allowed JSON-RPC requests to the loopback-only chain."""
import json
from pathlib import Path
import subprocess
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ALLOWED = frozenset(method for method, decision in
                    json.loads(Path(__file__).with_name("rpc_methods.json").read_text()).items()
                    if decision == "allow")
NODE_SIGNING = frozenset({
    "eth_sendTransaction", "eth_sendTransactionSync", "eth_sendUnsignedTransaction",
    "eth_sign", "eth_signTransaction", "eth_signTypedData", "eth_signTypedData_v3",
    "eth_signTypedData_v4", "personal_sign",
})
SIGNING_REFUSAL = "Sign locally and use eth_sendRawTransaction."
MAX_BODY = 2 * 1024 * 1024
REFUSALS = "/tmp/rpc-refusals.log"


def refusal(message):
    with open(REFUSALS, "a") as log:
        log.write(f"RPC refused: {message}\n")


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
                                     (SIGNING_REFUSAL if method in NODE_SIGNING else "Method is not allowed.")
                                     if valid else "Invalid JSON-RPC request."))
        # Reject the whole batch before forwarding any member.
        if refused:
            return [error(request, -32601, SIGNING_REFUSAL if isinstance(request, dict) and
                          isinstance(request.get("method"), str) and
                          request.get("method") in NODE_SIGNING else "Batch contains a refused method.")
                    for request in requests] if batch else refused[0]
        data = json.dumps(payload).encode()
        request = urllib.request.Request("http://127.0.0.1:8546", data, {"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=15) as response:
            body = response.read(MAX_BODY + 1)
            if len(body) > MAX_BODY:
                return error(None, -32000, "Chain response too large.")
            return json.loads(body)

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

    def handle_error(self, request, address):
        # Disconnected clients cannot produce unlimited traceback output.
        refusal("HTTP connection failed.")


def main():
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
    Server(("0.0.0.0", 8545), Chain()).serve_forever()


if __name__ == "__main__":
    main()
