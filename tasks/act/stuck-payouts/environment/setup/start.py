"""Run the shared chain starter, then replay the payout run before releasing the healthcheck."""
from pathlib import Path
import os
import subprocess
import sys
import time


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
        subprocess.run([sys.executable, "/setup/seed.py"], check=True, timeout=max(1, deadline - time.monotonic()))
        Path("/tmp/payouts-ready").touch()
        process.wait()
        raise RuntimeError("The shared chain starter exited.")
    finally:
        process.terminate()


if __name__ == "__main__":
    main()
