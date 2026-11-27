"""Replay last night's payout run: confirmed payouts, one lost broadcast, the rest queued behind it, and a retry."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import subprocess
import time
import urllib.request

URL = "http://127.0.0.1:8546"
TRANSFER = "transfer(address,uint256)"
GAS_LIMIT = "60000"
MAX_FEE = "30gwei"
TIP = "1gwei"
CONFIRMED = 22  # rows 1-22 land; row 23's broadcast is lost; rows 24-40 and row 23's retry wait behind it

# (contributor, USDC in cents, memo). Alice appears twice: her November work and a travel reimbursement.
ROWS = [
    ("ana.eth", 420000, "november: indexer work"),
    ("bruno", 185000, "november: docs"),
    ("chen", 310000, "november: frontend"),
    ("dmitri", 95000, "november: support rotation"),
    ("alice", 275000, "november: protocol work"),
    ("fatima", 160000, "november: design"),
    ("gabriel", 230000, "november: audits follow-up"),
    ("hana", 120000, "november: community calls"),
    ("ivan", 345000, "november: contracts"),
    ("jules", 80000, "november: translations"),
    ("kofi", 210000, "november: devrel"),
    ("lena", 150000, "november: QA"),
    ("marco", 265000, "november: backend"),
    ("nadia", 99000, "november: grants review"),
    ("omar", 380000, "november: infra"),
    ("priya", 175000, "november: research"),
    ("quentin", 60000, "november: bug bounty triage"),
    ("rosa", 220000, "november: frontend"),
    ("sven", 135000, "november: data dashboards"),
    ("tomas", 290000, "november: contracts"),
    ("uma", 110000, "november: moderation"),
    ("victor", 240000, "november: backend"),
    ("alice", 64250, "reimbursement: devcon travel"),
    ("wen", 195000, "november: SDK"),
    ("xavier", 125000, "november: docs"),
    ("yara", 330000, "november: protocol work"),
    ("zane", 90000, "november: support rotation"),
    ("abebe", 205000, "november: indexer work"),
    ("beatriz", 145000, "november: design"),
    ("carlos.eth", 360000, "november: contracts"),
    ("dalia", 70000, "november: translations"),
    ("emeka", 255000, "november: infra"),
    ("freya", 115000, "november: community calls"),
    ("goran", 285000, "november: backend"),
    ("hiro", 165000, "november: QA"),
    ("ines", 100000, "november: grants review"),
    ("jakub", 225000, "november: frontend"),
    ("kira", 140000, "november: research"),
    ("liam", 310000, "november: contracts"),
    ("mei", 85000, "november: devrel"),
]


def rpc(method, params):
    request = urllib.request.Request(URL, json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": method, "params": params,
    }).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=60) as response:
        result = json.load(response)
    if "error" in result:
        raise RuntimeError(f"{method} failed: {result['error']}")
    return result["result"]


def cast(*args):
    return subprocess.check_output(["cast", *args], text=True).strip()


def stamp(seconds):
    return datetime.fromtimestamp(seconds, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def signed(token, key, to, amount, nonce):
    return cast("mktx", token, TRANSFER, to, str(amount), "--private-key", key, "--rpc-url", URL,
                "--nonce", str(nonce), "--gas-limit", GAS_LIMIT, "--gas-price", MAX_FEE,
                "--priority-gas-price", TIP, "--chain", "31337")


def receipt_of(tx_hash):
    for _ in range(300):
        receipt = rpc("eth_getTransactionReceipt", [tx_hash])
        if receipt:
            return receipt
        time.sleep(0.1)
    raise RuntimeError(f"{tx_hash} was not mined during setup.")


def write(path, text):
    path.write_text(text)
    path.chmod(0o444)


def main():
    context = json.loads(Path("/chain/chain_context.json").read_text())
    private_path = Path("/private/private_chain_context.json")
    private = json.loads(private_path.read_text())
    key, wallet, token = context["privateKey"], context["wallet"], context["usdc"]

    addresses = {}
    payouts = []
    for index, (contributor, cents, memo) in enumerate(ROWS, start=1):
        if contributor not in addresses:
            addresses[contributor] = cast("to-check-sum-address", "0x" + secrets.token_hex(20))
        payouts.append({"id": index, "contributor": contributor, "address": addresses[contributor],
                        "amount": cents * 10_000, "cents": cents, "memo": memo})

    rows = ["id,contributor,address,amount_usdc,memo"]
    rows += [f"{p['id']},{p['contributor']},{p['address']},{p['cents'] // 100}.{p['cents'] % 100:02d},{p['memo']}"
             for p in payouts]
    write(Path("/chain/payouts.csv"), "\n".join(rows) + "\n")

    start = int(rpc("eth_getBlockByNumber", ["latest", False])["timestamp"], 16) + 3600
    clock = start
    log = [f"{stamp(clock)} INFO  payout run 2026-11 started: {len(payouts)} rows from payouts.csv, "
           f"wallet {wallet}, next nonce {int(rpc('eth_getTransactionCount', [wallet, 'latest']), 16)}"]
    confirmed, lost, queued = [], [], []
    for nonce, payout in enumerate(payouts):
        amount = f"{payout['cents'] // 100}.{payout['cents'] % 100:02d}"
        head = f"id={payout['id']} to={payout['address']} amount={amount} USDC nonce={nonce}"
        raw = signed(token, key, payout["address"], payout["amount"], nonce)
        tx_hash = cast("keccak", raw)
        clock += 2
        if nonce < CONFIRMED:
            rpc("evm_setNextBlockTimestamp", [clock + 10])
            rpc("eth_sendRawTransaction", [raw])
            receipt = receipt_of(tx_hash)
            if receipt["status"] != "0x1":
                raise RuntimeError(f"Payout {payout['id']} did not confirm during setup.")
            log.append(f"{stamp(clock)} INFO  {head} tx={tx_hash} broadcast")
            clock += 11
            log.append(f"{stamp(clock)} INFO  id={payout['id']} tx={tx_hash} confirmed in block "
                       f"{int(receipt['blockNumber'], 16)}")
            confirmed.append(tx_hash)
        elif nonce == CONFIRMED:
            log.append(f"{stamp(clock)} ERROR {head} tx={tx_hash} broadcast failed: socket hang up (ECONNRESET)")
            log.append(f"{stamp(clock)} WARN  id={payout['id']} left for the retry sweep")
            lost.append(tx_hash)
        else:
            rpc("eth_sendRawTransaction", [raw])
            log.append(f"{stamp(clock)} INFO  {head} tx={tx_hash} broadcast")
            clock += 120
            log.append(f"{stamp(clock)} WARN  id={payout['id']} tx={tx_hash} no receipt after 120s, moving on")
            queued.append(tx_hash)
    clock += 1
    log.append(f"{stamp(clock)} INFO  payout run 2026-11 finished: {len(confirmed)} confirmed, "
               f"{len(payouts) - len(confirmed)} unconfirmed")
    clock += 4
    log.append(f"{stamp(clock)} INFO  retry sweep started for {len(lost)} failed broadcast(s)")
    # The sweep re-signs each failed payout at the bot's next local nonce, which also waits behind the gap.
    retries = []
    for payout in (p for p in payouts if p["id"] == CONFIRMED + 1):
        nonce = len(payouts)
        amount = f"{payout['cents'] // 100}.{payout['cents'] % 100:02d}"
        raw = signed(token, key, payout["address"], payout["amount"], nonce)
        tx_hash = cast("keccak", raw)
        rpc("eth_sendRawTransaction", [raw])
        clock += 1
        log.append(f"{stamp(clock)} INFO  retry sweep: id={payout['id']} to={payout['address']} amount={amount} USDC "
                   f"nonce={nonce} tx={tx_hash} broadcast")
        retries.append(tx_hash)
    clock += 2
    log.append(f"{stamp(clock)} ERROR retry sweep: process exited with code 137 (out of memory)")
    write(Path("/chain/payout-bot.log"), "\n".join(log) + "\n")

    for tx_hash in queued + retries:
        if rpc("eth_getTransactionByHash", [tx_hash]) is None:
            raise RuntimeError("A queued payout left the pool during setup.")
    if int(rpc("eth_getTransactionCount", [wallet, "latest"]), 16) != CONFIRMED:
        raise RuntimeError("The wallet nonce does not stop at the lost payout.")

    rpc("anvil_setTime", [int(time.time())])
    rpc("evm_mine", [])
    private.update(payouts=[{key_: p[key_] for key_ in ("id", "contributor", "address", "amount")} for p in payouts],
                   confirmedHashes=confirmed, lostHashes=lost, queuedHashes=queued, retryHashes=retries,
                   seedBlock=int(rpc("eth_blockNumber", []), 16))
    os.chmod(private_path, 0o644)
    write(private_path, json.dumps(private, indent=2) + "\n")


if __name__ == "__main__":
    main()
