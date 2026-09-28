import json
import os
import subprocess
from pathlib import Path


def cast(*args):
    return subprocess.check_output(["cast", *args, "--rpc-url", os.environ["RPC_URL"]], text=True).strip()


setup = json.loads(Path("private.json").read_text())
balance = int(cast("call", setup["token"], "balanceOf(address)(uint256)", setup["recipient"]).split()[0])
latest = int(cast("block-number"))
transactions = []
for block in range(setup["setup_block"] + 1, latest + 1):
    result = json.loads(cast("rpc", "eth_getBlockByNumber", hex(block), "true"))
    transactions.extend(result["transactions"])
sent = len(transactions) == 1 and transactions[0]["from"].lower() == setup["sender"].lower()
print(json.dumps({
    "recipient_balance": {"passed": balance == 12_500_000, "reason": f"Recipient holds {balance} base units; expected 12500000."},
    "agent_sender": {"passed": sent, "reason": "One transaction came from the agent key." if sent else "Expected one transaction from the agent key."},
}))
