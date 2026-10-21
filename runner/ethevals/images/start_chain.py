"""Prepare a declared chain sidecar before its healthcheck releases the agent."""
from pathlib import Path
import os
import shutil
import subprocess
import sys
import time

from rpc_filter import redact, rpc


def main():
    public = Path("/chain")
    private = Path("/private")
    public.mkdir(exist_ok=True)
    private.mkdir(exist_ok=True)
    private.chmod(0o700)
    chain_env = os.environ.copy()
    fork_url = os.environ.pop("FORK_RPC_URL", None)
    process = subprocess.Popen([sys.executable, "/opt/rpc_filter.py"], env=chain_env)
    del chain_env
    try:
        for _ in range(300):
            try:
                rpc("eth_chainId")
                break
            except Exception:
                if process.poll() is not None:
                    raise RuntimeError("The RPC filter exited during setup.")
                time.sleep(0.1)
        else:
            raise RuntimeError("The chain did not start.")
        shutil.copytree("/setup", "/eval/setup")
        shutil.copyfile("/opt/setup-foundry.toml", "/eval/foundry.toml")
        setup = subprocess.run(["forge", "script", "setup/setup.s.sol", "--broadcast", "--slow",
                                "--rpc-url", "http://127.0.0.1:8546"], cwd="/eval",
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        print(redact(setup.stdout, [fork_url]), end="", flush=True)
        setup.check_returncode()
        rpc("anvil_setIntervalMining", [0])
        rpc("evm_setAutomine", [True])
        for directory, name in ((public, "chain_context.json"), (private, "private_chain_context.json")):
            shutil.copyfile(Path("/eval") / name, directory / name)
            (directory / name).chmod(0o444)
        Path("/tmp/chain-ready").touch()
        process.wait()
        raise RuntimeError(f"The RPC filter exited with code {process.returncode}.")
    finally:
        process.terminate()


if __name__ == "__main__":
    main()
