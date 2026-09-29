#!/usr/bin/env python3
import json
import os
import subprocess
from pathlib import Path


def cast(*args):
    return subprocess.check_output(["cast", *args, "--rpc-url", os.environ["RPC_URL"]], text=True).strip()


setup = json.loads(Path("private.json").read_text())
balance = int(cast("call", setup["token"], "balanceOf(address)(uint256)", setup["recipient"]).split()[0])
sent = int(cast("nonce", setup["sender"])) == 1
print(json.dumps({
    "recipient_balance": {"passed": balance == 12_500_000, "reason": f"Recipient holds {balance} base units; expected 12500000."},
    "agent_sender": {"passed": sent, "reason": "One transaction came from the agent key." if sent else "Expected one transaction from the agent key."},
}))
