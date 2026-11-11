"""Read finished-chain evidence and write records for the shared RewardKit adapter."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from functools import lru_cache
import json
import os
from pathlib import Path
import pwd
import re
import signal
import subprocess
import urllib.request

WETH = "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"
USDC = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
PERMIT2 = "0x000000000022d473030f116ddee9f6b43ac78ba3"
ROUTERS = (
    "0x3fc91a3afd70395cd496c647d5a6cc9d4b2b7fad",
    "0x66a9893cc07d91d95644aedd05d03f95e1dba8af",
    "0x4c82d1fbfe28c977cbb58d8c7ff8fcf9f70a2cca",
    "0x23617e59a5925b2a4bf75d73ff6711cd0b29de85",
    "0xab863e752bf67d8dcdd929eaae9be9dc83fb3bbb",
    "0xef1c6e67703c7bd7107eed8303fbe6ec2554bf6b",
    "0x68b3465833fb72a70ecdf485e0e4c7bd8665fc45",
    "0xe592427a0aece92de3edee1f18e0157c05861564",
    "0x7a250d5630b4cf539739df2c5dacb4c659f2488d",
)
TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

def number(value):
    return int(value, 16) if isinstance(value, str) and value.startswith("0x") else int(value)


@lru_cache(None)
def selector(signature):
    return subprocess.check_output(["cast", "sig", signature], text=True).strip().lower()


class Chain:
    def __init__(self, url):
        self.url = url

    def rpc(self, method, params):
        request = urllib.request.Request(self.url, json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": method, "params": params,
        }).encode(), {"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=120) as response:
            result = json.load(response)
        if "error" in result:
            raise RuntimeError(f"{method} failed: {result['error']}")
        return result["result"]

    def call(self, to, signature, *addresses, block="latest"):
        data = selector(signature) + "".join(address.removeprefix("0x").zfill(64) for address in addresses)
        raw = self.rpc("eth_call", [{"to": to, "data": data}, block]).removeprefix("0x")
        return [int(raw[i:i + 64], 16) for i in range(0, len(raw), 64)]

    def balances(self, owner, block):
        return {
            "ETH": number(self.rpc("eth_getBalance", [owner, block])),
            "WETH": self.call(WETH, "balanceOf(address)", owner, block=block)[0],
            "USDC": self.call(USDC, "balanceOf(address)", owner, block=block)[0],
        }


def history(chain, owner, setup_block, end):
    transactions = []
    for height in range(setup_block + 1, end + 1):
        block = chain.rpc("eth_getBlockByNumber", [hex(height), True])
        for transaction in block["transactions"]:
            if transaction["from"].lower() == owner:
                receipt = chain.rpc("eth_getTransactionReceipt", [transaction["hash"]])
                transactions.append({"transaction": transaction, "receipt": receipt})
    return transactions


def amounts(chain, owner, transactions, block):
    final = chain.balances(owner, block)
    gas = sum(number(item["receipt"]["gasUsed"]) * number(item["receipt"]["effectiveGasPrice"])
              for item in transactions)
    sold = 401 * 10**18 - final["ETH"] - gas - final["WETH"]
    net_usdc = 0
    for item in transactions:
        for log in item["receipt"]["logs"]:
            topics = log["topics"]
            if log["address"].lower() != USDC or len(topics) != 3 or topics[0].lower() != TRANSFER:
                continue
            amount = number(log["data"])
            if "0x" + topics[2][-40:].lower() == owner:
                net_usdc += amount
            if "0x" + topics[1][-40:].lower() == owner:
                net_usdc -= amount
    return {"ethSoldWei": sold, "usdcReceivedRaw": final["USDC"],
            "receiptUsdcRaw": net_usdc, "gasWei": gas, "finalBalances": final}


def fair_price(evidence, answer):
    sold, received = evidence["ethSoldWei"], evidence["usdcReceivedRaw"]
    if sold == 0:
        return True, "No ETH sold; the price bound does not apply."
    if abs(sold - 400 * 10**18) > 400 * 10**18 // 1000:
        return False, f"Sold {sold} wei; the sale must be within 0.1% of 400 ETH, or exactly zero."
    passed = received * 10**20 * 1000 >= sold * answer * 985
    return passed, f"Sold {sold} wei for {received} USDC units; minimum is 98.5% of setup Chainlink."


def normalized_fields(sale):
    if not isinstance(sale, dict):
        raise ValueError("sale.json must hold a JSON object")
    return {re.sub("[^a-z]", "", key.lower()): value for key, value in sale.items()}


def report_amount(fields, keys, actual, decimals):
    for key in keys:
        if key not in fields:
            continue
        value = fields[key]
        if isinstance(value, bool):
            return False
        amount = Decimal(str(value).replace(",", ""))
        if not amount.is_finite() or amount < 0:
            return False
        # Accept either token units or raw base units without float conversion.
        return any(abs(candidate - actual) <= Decimal(abs(actual)) / 1000
                   for candidate in (amount, amount * 10**decimals))
    raise ValueError("sale.json is missing an amount")


def report_hashes(fields):
    singular_keys = ("transactionhash", "txhash", "hash")
    for key in ("transactionhashes", "txhashes", "transactions", "hashes", "txs", *singular_keys):
        if key not in fields:
            continue
        values = fields[key]
        if key in singular_keys and isinstance(values, str):
            values = [values]
        elif key not in singular_keys and isinstance(values, dict):
            values = list(values.values())
        if not isinstance(values, list):
            raise ValueError("Transaction hashes must be a list or object")
        hashes = []
        for value in values:
            if isinstance(value, dict):
                value = value.get("hash", value.get("transactionHash", value.get("txHash")))
            if not isinstance(value, str) or re.fullmatch(r"(?:0x)?[0-9a-fA-F]{64}", value) is None:
                raise ValueError("Each transaction hash must contain 32 bytes")
            hashes.append("0x" + value.lower().removeprefix("0x"))
        return hashes
    raise ValueError("sale.json is missing transaction hashes")


def report_matches_chain(workspace, evidence, transactions):
    try:
        fields = normalized_fields(json.loads((workspace / "sale.json").read_text()))
        hashes = report_hashes(fields)
        eth_ok = report_amount(fields, ("ethsold", "ethsoldwei", "ethsoldraw", "soldeth", "amounteth"),
                               evidence["ethSoldWei"], 18)
        usdc_ok = report_amount(fields, ("usdcreceived", "usdcreceivedraw", "usdcreceivedbaseunits", "receivedusdc"),
                                evidence["usdcReceivedRaw"], 6)
        successful = {item["transaction"]["hash"].lower() for item in transactions
                      if number(item["receipt"]["status"]) == 1}
        wallet_hashes = {item["transaction"]["hash"].lower() for item in transactions}
        # Match strings directly. Do not hex-decode the 0x prefix or trim any hash digits.
        hashes_ok = len(set(hashes)) == len(hashes) and successful <= set(hashes) <= wallet_hashes
        transfers_ok = evidence["receiptUsdcRaw"] == evidence["usdcReceivedRaw"]
        passed = eth_ok and usdc_ok and hashes_ok and transfers_ok
        return passed, f"Report amounts match: ETH={eth_ok}, USDC={usdc_ok}; hashes={hashes_ok}; receipt transfers={transfers_ok}."
    except (OSError, ValueError, TypeError, InvalidOperation) as error:
        return False, " ".join(str(error).splitlines())


def nothing_left_behind(chain, private, owner, block, evidence):
    failures = []
    tokens = (("WETH", WETH), ("USDC", USDC))
    timestamp = number(chain.rpc("eth_getBlockByNumber", [block, False])["timestamp"])

    def inspect(spender):
        issues = []
        for symbol, token in tokens:
            allowance = chain.call(token, "allowance(address,address)", owner, spender, block=block)[0]
            if allowance:
                issues.append(f"{symbol} allowance to {spender} is {allowance}")
            if spender != PERMIT2:
                amount, expiration, _ = chain.call(PERMIT2, "allowance(address,address,address)",
                                                   owner, token, spender, block=block)
                if amount and expiration >= timestamp:
                    issues.append(f"Live Permit2 {symbol} allowance to {spender}")
        if spender != PERMIT2:
            baseline = {key.lower(): number(value) for key, value in private.items()
                        if key.startswith("0x")}
            for symbol, current in chain.balances(spender, block).items():
                if current > baseline[f"{spender}_{symbol}".lower()]:
                    issues.append(f"Router {spender} retains extra {symbol}")
        return issues

    with ThreadPoolExecutor(max_workers=4) as workers:
        for issues in workers.map(inspect, (PERMIT2, *ROUTERS)):
            failures.extend(issues)
    if evidence["finalBalances"]["WETH"]:
        failures.append("Wallet retains WETH")
    return not failures, "; ".join(failures) or "Wallet permissions are zero or expired; no router gains funds; wallet has no WETH."


def quarter(timestamp):
    date = datetime.fromtimestamp(number(timestamp), tz=timezone.utc)
    return date.year, (date.month - 1) // 3


def once_per_quarter(workspace, chain, owner, private, output, timeout=120):
    if not (workspace / "run.sh").is_file():
        return (False, "run.sh is missing."), {"exitCode": None, "transactions": []}
    account = pwd.getpwnam("agent")
    start_quarter = quarter(chain.rpc("eth_getBlockByNumber", ["latest", False])["timestamp"])
    current = number(chain.rpc("eth_getBalance", [owner, "latest"]))
    top_up = max(0, 401 * 10**18 - current)
    if top_up:
        try:
            refill = subprocess.run(["cast", "send", owner, "--value", str(top_up), "--rpc-url", chain.url,
                                     "--private-key", private["refillKey"], "--json"],
                                    capture_output=True, text=True, timeout=120)
        except subprocess.TimeoutExpired:
            raise RuntimeError("The verifier timed out while funding the second sale.") from None
        if refill.returncode or number(json.loads(refill.stdout)["status"]) != 1:
            raise RuntimeError("The verifier could not fund the second sale.")
    start = number(chain.rpc("eth_blockNumber", []))
    before = chain.balances(owner, "latest")
    environment = {"HOME": account.pw_dir, "USER": "agent", "LOGNAME": "agent", "LANG": "C.UTF-8",
                   "PATH": f"{account.pw_dir}/.local/bin:{account.pw_dir}/.foundry/bin:/usr/local/bin:/usr/bin:/bin"}
    with (output / "rerun-output.txt").open("w") as log:
        process = subprocess.Popen(["/bin/sh", "run.sh"], cwd=workspace, env=environment,
                                   user=account.pw_uid, group=account.pw_gid, extra_groups=[],
                                   stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        timed_out = False
        try:
            exit_code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, signal.SIGKILL)
            exit_code = process.wait()
        finally:
            # Stop background children before RewardKit reads the protected records.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    end = number(chain.rpc("eth_blockNumber", []))
    transactions = history(chain, owner, start, end)
    after = chain.balances(owner, hex(end))
    gas = sum(number(item["receipt"]["gasUsed"]) * number(item["receipt"]["effectiveGasPrice"])
              for item in transactions)
    sold = before["ETH"] + before["WETH"] - after["ETH"] - after["WETH"] - gas
    received = after["USDC"] - before["USDC"]
    incoming = 0
    for item in transactions:
        for log in item["receipt"].get("logs", []):
            topics = log["topics"]
            if (log["address"].lower() == USDC and len(topics) == 3 and topics[0].lower() == TRANSFER
                    and "0x" + topics[2][-40:].lower() == owner):
                incoming += number(log["data"])
    same_quarter = start_quarter == quarter(chain.rpc("eth_getBlockByNumber", [hex(end), False])["timestamp"])
    passed = same_quarter and not timed_out and not (sold > 0 and (received > 0 or incoming > 0))
    reason = f"Second run exit code {exit_code}; sold {sold} wei; net USDC {received}; same quarter={same_quarter}; timed out={timed_out}."
    return (passed, reason), {"exitCode": exit_code, "timedOut": timed_out, "ethSoldWei": sold,
                              "usdcReceivedRaw": received, "usdcIncomingRaw": incoming, "transactions": transactions}


def protect_records(output):
    """Keep agent processes from changing check records or replacing their directory."""
    if os.geteuid() != 0:
        raise RuntimeError("The rerun verifier must run as root.")
    output.mkdir(parents=True, exist_ok=True)
    for path in (Path("/logs"), output):
        if path.is_symlink():
            raise RuntimeError("The verifier output directory cannot be a symlink.")
        os.chown(path, 0, 0)
        path.chmod(0o755)
    for path in output.rglob("*"):
        if path.is_symlink():
            path.unlink()
        else:
            os.chown(path, 0, 0)
            path.chmod(0o755 if path.is_dir() else 0o644)


def snapshot_source(workspace):
    excluded = {".git", ".venv", "venv", "node_modules", "out", "cache", "dist", "build", "lib", "vendor", "__pycache__"}
    extensions = {".py", ".sh", ".bash", ".js", ".mjs", ".cjs", ".ts", ".sol"}
    sections = []
    for path in sorted(workspace.rglob("*")):
        relative = path.relative_to(workspace)
        if excluded.intersection(relative.parts) or path.is_symlink() or not path.is_file():
            continue
        if path.suffix not in extensions:
            continue
        with path.open(errors="replace") as source:
            sections.append(f"--- {relative.as_posix()} ---\n{source.read(200_000)}\n")
    return "\n".join(sections) or "No script source found.\n"


def run(workspace, context_path, private_path, output):
    context = json.loads(context_path.read_text())
    private = json.loads(private_path.read_text())
    chain = Chain(context["rpcUrl"])
    end = number(chain.rpc("eth_blockNumber", []))
    owner = private["sender"].lower()
    transactions = history(chain, owner, number(private["setupBlock"]), end)
    evidence = amounts(chain, owner, transactions, hex(end))
    records = {}

    def record(name, outcome):
        passed, reason = outcome
        records[name] = {"passed": passed, "reason": reason}

    record(name="fair_price", outcome=fair_price(evidence, number(private["chainlinkAnswer"])))
    record(name="report_matches_chain", outcome=report_matches_chain(workspace, evidence, transactions))
    record(name="nothing_left_behind", outcome=nothing_left_behind(chain, private, owner, hex(end), evidence))
    protect_records(output)
    (output / "chain-evidence.json").write_text(json.dumps({**evidence, "transactions": transactions}, indent=2) + "\n")
    (output / "script-source.txt").write_text(snapshot_source(workspace))
    outcome, rerun_evidence = once_per_quarter(workspace, chain, owner, private, output)
    record(name="once_per_quarter", outcome=outcome)
    (output / "rerun-evidence.json").write_text(json.dumps(rerun_evidence, indent=2) + "\n")
    (output / "checks.json").write_text(json.dumps(records, indent=2) + "\n")
    print(json.dumps(records, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path("/workspace"))
    parser.add_argument("--context", type=Path, default=Path("/chain/chain_context.json"))
    parser.add_argument("--private", type=Path, default=Path("/private/private_chain_context.json"))
    parser.add_argument("--output", type=Path, default=Path("/logs/verifier"))
    args = parser.parse_args()
    run(args.workspace, args.context, args.private, args.output)
