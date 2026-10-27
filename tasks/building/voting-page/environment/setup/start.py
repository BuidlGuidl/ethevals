"""Run the shared chain starter, then seed before releasing the healthcheck."""
from pathlib import Path
import os
import subprocess
import sys
import time

from seed import states


def main():
    environment = dict(os.environ, PATH="/setup/bin:" + os.environ["PATH"])
    process = subprocess.Popen([sys.executable, "/opt/start_chain.py"], env=environment)
    try:
        deadline = time.monotonic() + 600
        while not Path("/tmp/chain-ready").exists():
            if process.poll() is not None:
                raise RuntimeError("The shared chain starter exited.")
            if time.monotonic() >= deadline:
                raise TimeoutError("The shared chain starter exceeded ten minutes.")
            time.sleep(0.1)
        subprocess.run([sys.executable, "/setup/seed.py", "seed", "--rpc-url", "http://127.0.0.1:8546",
                        "--contracts", "/opt/governance"], check=True, timeout=max(1, deadline - time.monotonic()))
        states("http://127.0.0.1:8546", Path("/private/private_chain_context.json"))
        Path("/tmp/voting-ready").touch()
        process.wait()
        raise RuntimeError("The shared chain starter exited.")
    finally:
        process.terminate()


if __name__ == "__main__":
    main()
