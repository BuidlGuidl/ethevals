import json
import os
import secrets
import subprocess
from pathlib import Path


def cast(*args):
    return subprocess.check_output(["cast", *args], text=True).strip()


rpc = os.environ["RPC_URL"]
key = "0x" + secrets.token_hex(32)
sender = cast("wallet", "address", "--private-key", key)
recipient = cast("wallet", "address", "--private-key", "0x" + secrets.token_hex(32))
deployer = "0x" + secrets.token_hex(32)
deployer_address = cast("wallet", "address", "--private-key", deployer)
for address in (sender, deployer_address):
    cast("rpc", "--rpc-url", rpc, "anvil_setBalance", address, "0x8ac7230489e80000")
compiled = json.loads(subprocess.check_output([
    os.environ["SOLC"], "--combined-json", "bin", "scorer/Token.sol"], text=True))
bytecode = compiled["contracts"]["scorer/Token.sol:Token"]["bin"]
argument = cast("abi-encode", "constructor(address)", sender)[2:]
receipt = json.loads(cast("send", "--rpc-url", rpc, "--private-key", deployer, "--json", "--create", bytecode + argument))
token = receipt["contractAddress"]
public = {"rpc_url": "http://chain:8545", "private_key": key, "sender": sender,
          "recipient": recipient, "token": token}
Path("private.json").write_text(json.dumps({**public, "setup_block": int(receipt["blockNumber"], 16)}))
print(json.dumps({"files": {"chain.json": json.dumps(public) + "\n"}}))
