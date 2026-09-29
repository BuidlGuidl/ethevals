#!/usr/bin/env python3
import json
import os
import subprocess
from pathlib import Path


def cast(*args):
    # The check reads the unfiltered RPC after the runner stops the agent and settles mining.
    return subprocess.check_output(["cast", *args, "--rpc-url", os.environ["RPC_URL"]], text=True).strip()


# Trust setup's private copy, not chain.json, which the agent can edit.
setup = json.loads(Path("private.json").read_text())
# Check the actual recipient balance and require exactly one transaction from the funded sender.
balance = int(cast("call", setup["token"], "balanceOf(address)(uint256)", setup["recipient"]).split()[0])
sent = int(cast("nonce", setup["sender"])) == 1
# Six decimals make 12.5 tokens equal 12,500,000 base units. Missing work returns failed checks.
print(json.dumps({
    "recipient_balance": {"passed": balance == 12_500_000, "reason": f"Recipient holds {balance} base units; expected 12500000."},
    "agent_sender": {"passed": sent, "reason": "One transaction came from the agent key." if sent else "Expected one transaction from the agent key."},
}))
