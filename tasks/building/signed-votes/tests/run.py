"""Run the module on a verifier-only fork with disposable wallet fixtures."""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request


def main():
    submission = Path(sys.argv[1] if len(sys.argv) > 1 else "/workspace/src/votes.ts").resolve()
    output = Path(sys.argv[2] if len(sys.argv) > 2 else "/logs/verifier").resolve()
    deps = Path(os.environ.get("VOTES_DEPS", "/opt/votes-deps")).resolve()
    output.mkdir(parents=True, exist_ok=True)
    upstream = os.environ.get("RPC_URL", "http://chain:8545")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    rpc_url = f"http://127.0.0.1:{port}"
    with tempfile.TemporaryDirectory(prefix="votes-verifier-") as directory:
        root = Path(directory)
        root.chmod(0o700)
        for name in ("votes.mjs", "wallets.mjs"):
            shutil.copyfile(Path(__file__).with_name(name), root / name)
        (root / "node_modules").symlink_to(deps / "node_modules", target_is_directory=True)
        chain = subprocess.Popen([
            "anvil", "--fork-url", upstream, "--host", "127.0.0.1", "--port", str(port),
            "--accounts", "0", "--silent",
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(300):
                if chain.poll() is not None:
                    raise RuntimeError("The verifier fork exited during startup.")
                try:
                    request = urllib.request.Request(rpc_url, json.dumps({
                        "jsonrpc": "2.0", "id": 1, "method": "eth_chainId", "params": [],
                    }).encode(), {"Content-Type": "application/json"})
                    with urllib.request.urlopen(request, timeout=1) as response:
                        if json.load(response).get("result") == "0x1":
                            break
                except OSError:
                    pass
                time.sleep(0.1)
            else:
                raise RuntimeError("The verifier fork did not start.")
            env = os.environ.copy()
            env["RPC_URL"] = rpc_url
            with (output / "votes.log").open("w") as log:
                result = subprocess.run([
                    "node", "--import", str(deps / "node_modules/tsx/dist/loader.mjs"),
                    str(root / "votes.mjs"), str(submission), str(output),
                ], env=env, stdout=log, stderr=subprocess.STDOUT, timeout=420)
            if result.returncode:
                raise RuntimeError("The vote checks failed to run. Read votes.log.")
        finally:
            chain.terminate()
            try:
                chain.wait(timeout=5)
            except subprocess.TimeoutExpired:
                chain.kill()
                chain.wait()


if __name__ == "__main__":
    main()
