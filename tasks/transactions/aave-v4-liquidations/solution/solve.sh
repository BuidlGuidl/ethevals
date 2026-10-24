#!/bin/sh
set -eu
cd /workspace
test -r chain_context.json
test ! -r /private/private_chain_context.json
python3 - <<'PY'
import json
from decimal import Decimal
from pathlib import Path
import subprocess

chain = json.loads(Path("chain_context.json").read_text())
rpc = chain["rpcUrl"]
spoke = chain["spoke"]
key = chain["privateKey"]
usdc = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
tokens = {0: ("0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2", 18),
          3: ("0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599", 8)}
maximum = str(2**256 - 1)


def call(signature, *args):
    return json.loads(subprocess.check_output(
        ["cast", "call", spoke, signature, *map(str, args), "--rpc-url", rpc, "--json"], text=True))


def send(target, signature, *args):
    estimate = int(subprocess.check_output(
        ["cast", "estimate", target, signature, *map(str, args), "--from", chain["wallet"],
         "--rpc-url", rpc], text=True).strip())
    receipt = json.loads(subprocess.check_output(
        ["cast", "send", target, signature, *map(str, args), "--private-key", key,
         "--rpc-url", rpc, "--gas-limit", str(estimate * 3 // 2), "--json"], text=True))
    if int(receipt["status"], 16) != 1:
        raise RuntimeError(f"Transaction failed: {receipt['transactionHash']}")
    return receipt


send(usdc, "approve(address,uint256)", spoke, maximum)
topic = subprocess.check_output(["cast", "keccak",
    "LiquidationCall(uint256,uint256,address,address,bool,uint256,uint256,(int256,int256,uint256),uint256,uint256,uint256)"], text=True).strip().lower()
report = []
for borrower in chain["watchlist"]:
    for collateral in tokens:
        account = call("getUserAccountData(address)((uint256,uint256,uint256,uint256,uint256,uint256,uint256))", borrower)
        if isinstance(account[0], list):
            account = account[0]
        if int(account[2]) >= 10**18:
            break
        if int(call("getUserSuppliedAssets(uint256,address)(uint256)", collateral, borrower)[0]) == 0:
            continue
        receipt = send(spoke, "liquidationCall(uint256,uint256,address,uint256,bool)", collateral, 7, borrower, maximum, "false")
        for log in receipt["logs"]:
            if log["address"].lower() != spoke.lower() or log["topics"][0].lower() != topic:
                continue
            words = [int(log["data"][i:i + 64], 16) for i in range(2, len(log["data"]), 64)]
            token, decimals = tokens[int(log["topics"][1], 16)]
            seized = words[7] * words[9] // words[8]
            report.append({"borrower": borrower, "debtRepaidUSDC": str(Decimal(words[2]) / 10**6),
                           "collateralSeized": {"token": token, "amount": str(Decimal(seized) / 10**decimals)}})
Path("liquidations.json").write_text(json.dumps(report, indent=2) + "\n")
PY
