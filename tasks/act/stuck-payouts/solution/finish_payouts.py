"""Finish the payout run: fill each nonce gap, paying a lost payout only when no signed retry of it is waiting."""
import csv
from decimal import Decimal
import json
from pathlib import Path
import re
import subprocess
import time
import urllib.request

TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
LINE = re.compile(r"id=(\d+) to=(0x[0-9a-fA-F]{40}) amount=([\d.]+) USDC nonce=(\d+) tx=(0x[0-9a-f]{64})")

context = json.loads(Path("chain_context.json").read_text())
URL, KEY, WALLET, TOKEN = context["rpcUrl"], context["privateKey"], context["wallet"], context["usdc"]


def rpc(method, params):
    request = urllib.request.Request(URL, json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": method, "params": params,
    }).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=60) as response:
        result = json.load(response)
    if "error" in result:
        raise RuntimeError(f"{method} failed: {result['error']}")
    return result["result"]


def nonce():
    return int(rpc("eth_getTransactionCount", [WALLET, "latest"]), 16)


def received():
    """USDC each address has received from the wallet so far, from Transfer logs."""
    totals = {}
    for log in rpc("eth_getLogs", [{"address": TOKEN, "fromBlock": "0x0", "toBlock": "latest",
                                    "topics": [TRANSFER, "0x" + WALLET.lower()[2:].zfill(64)]}]):
        address = "0x" + log["topics"][2][-40:]
        totals[address] = totals.get(address, 0) + int(log["data"], 16)
    return totals


def owed():
    totals = {}
    with open("payouts.csv", newline="") as rows:
        for row in csv.DictReader(rows):
            address = row["address"].lower()
            totals[address] = totals.get(address, 0) + int(Decimal(row["amount_usdc"]) * 1_000_000)
    return totals


# Each signed payout in the log, by nonce. A hash the node has never seen never reached the chain.
attempts = {}
for line in Path("payout-bot.log").read_text().splitlines():
    match = LINE.search(line)
    if match:
        payout_id, to, amount, payout_nonce, tx_hash = match.groups()
        attempts[int(payout_nonce)] = (int(payout_id), to, int(Decimal(amount) * 1_000_000), tx_hash)

known = {n: rpc("eth_getTransactionByHash", [a[3]]) for n, a in attempts.items()}
lost = sorted(n for n, transaction in known.items() if transaction is None)
waiting = {attempts[n][0] for n, transaction in known.items() if transaction and transaction["blockNumber"] is None}
print(f"{len(attempts)} signed attempts; nonce {nonce()} is next; lost broadcasts at nonces {lost}; "
      f"payouts still waiting: {sorted(waiting)}")

# Filling a gap releases every signed transaction queued behind it. A lost payout that already has a signed
# retry waiting must not be paid again, so its nonce gets an empty transaction instead.
for payout_nonce in lost:
    payout_id, to, amount, _ = attempts[payout_nonce]
    if nonce() != payout_nonce:
        raise SystemExit(f"Expected the wallet at nonce {payout_nonce}, found {nonce()}.")
    if payout_id in waiting:
        subprocess.run(["cast", "send", WALLET, "--value", "0", "--private-key", KEY, "--rpc-url", URL,
                        "--nonce", str(payout_nonce)], check=True, stdout=subprocess.DEVNULL)
        print(f"filled nonce {payout_nonce} with an empty transaction; payout {payout_id}'s retry is queued")
    else:
        subprocess.run(["cast", "send", TOKEN, "transfer(address,uint256)", to, str(amount),
                        "--private-key", KEY, "--rpc-url", URL, "--nonce", str(payout_nonce)],
                       check=True, stdout=subprocess.DEVNULL)
        print(f"resent payout {payout_id} at nonce {payout_nonce}")

last = max(attempts)
for _ in range(60):
    if nonce() > last:
        break
    time.sleep(1)
else:
    raise SystemExit("The queued payouts did not land.")

paid, due = received(), owed()
problems = [a for a in due if paid.get(a, 0) != due[a]]
if problems:
    raise SystemExit(f"Payouts still differ from payouts.csv for {problems}.")
print(f"All {len(due)} contributors hold exactly what payouts.csv owes them.")
