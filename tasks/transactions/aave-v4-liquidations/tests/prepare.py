"""Copy the report and chain events into Forge's private input file."""

import json
import os
import re
from decimal import Decimal
from pathlib import Path
import subprocess
import urllib.request


def rpc(url, method, params):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.load(response)
    if "error" in result:
        raise RuntimeError(result["error"])
    return result["result"]


def field(row, *names, default=...):
    normalized = {re.sub(r"[^a-z0-9]", "", key.lower()): value for key, value in row.items()}
    for name in names:
        key = re.sub(r"[^a-z0-9]", "", name.lower())
        if key in normalized:
            return normalized[key]
    if default is not ...:
        return default
    raise ValueError(f"Missing report field: {names[0]}")


def amount_number(value):
    text = str(value).strip()
    match = re.fullmatch(r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)(?:\s+[A-Za-z]+)?", text)
    if not match:
        raise ValueError("Report amounts must be numbers with optional token units")
    return Decimal(match[1])


def amounts(value, decimals):
    number = amount_number(value)
    if not number.is_finite() or number < 0:
        raise ValueError("Report amounts must be finite and nonnegative")
    return int(number), int(number * 10**decimals)


def token_name(value):
    """A token given as a symbol, an address, or an object holding one."""
    if isinstance(value, dict):
        value = field(value, "symbol", "token", "asset", "address", "name", default=None)
    return None if value is None else str(value).strip().lower()


def scalar(value, decimals):
    """An amount given as a number, a numeric string with an optional unit, or an object holding one."""
    if not isinstance(value, dict):
        return value
    human = field(value, "amount", "value", "human", "formatted", "amountHuman", "decimal", default=None)
    if human is not None:
        return human
    raw = field(value, "raw", "wei", "amountRaw", "base", "baseUnits", "rawAmount", default=None)
    if raw is None:
        raise ValueError("Report amounts must be numbers with optional token units")
    return str(amount_number(raw) / (Decimal(10) ** decimals))


def parse_report(report):
    if isinstance(report, dict):
        report = field(report, "liquidations")
    if not isinstance(report, list):
        raise ValueError("The report must contain a list of liquidations")
    tokens = {
        "weth": (0, 18), "eth": (0, 18), "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2": (0, 18),
        "wbtc": (3, 8), "btc": (3, 8), "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599": (3, 8),
    }
    rows = []
    for row in report:
        if not isinstance(row, dict):
            raise ValueError("Report entries must be objects")
        debt = field(row, "debtRepaidUSDC", "debtRepaid", "repaid", "repaidUSDC", "usdcRepaid",
                     "amountRepaid", "repayAmount", "debtRepaidAmount", "debtCovered", "debtToCover", default=0)
        debt = scalar(debt, 6)
        if debt is None or amount_number(debt) <= 0:
            continue
        borrower = field(row, "borrower", "user", "account", "borrowerAddress", "userAddress")
        collateral = field(row, "collateralSeized", "collateral", "collateralAmount", "seizedCollateral",
                           "seized", "amountSeized", "collateralReceived")
        token = None
        raw = None
        if isinstance(collateral, dict):
            token = token_name(field(collateral, "token", "asset", "symbol", "collateralToken", "collateralAsset",
                                     "address", default=None))
            amount = field(collateral, "amount", "amountSeized", "collateralAmount", "seized", "value", "human",
                           "formatted", default=None)
            raw = field(collateral, "raw", "wei", "amountRaw", "base", "baseUnits", "rawAmount", default=None)
        else:
            amount = collateral
        if token is None:
            token = token_name(field(row, "collateralToken", "collateralAsset", "token", "asset", "symbol",
                                     default=None))
        if token is None:
            parts = str(amount).rsplit(maxsplit=1)
            if len(parts) != 2:
                raise ValueError("Report collateral needs a token or a unit")
            token = parts[1].lower()
        if token not in tokens:
            raise ValueError(f"Unknown collateral token: {token}")
        reserve, decimals = tokens[token]
        if amount is None:
            if raw is None:
                raise ValueError("Report collateral needs an amount")
            amount = str(amount_number(raw) / (Decimal(10) ** decimals))
        raw_debt, human_debt = amounts(debt, 6)
        raw_collateral, human_collateral = amounts(amount, decimals)
        rows.append({
            "borrower": borrower, "collateralHuman": human_collateral, "collateralRaw": raw_collateral,
            "debtHuman": human_debt, "debtRaw": raw_debt, "reserveId": reserve,
        })
    return rows


def main():
    chain = json.loads(Path(os.environ.get("AAVE_CONTEXT", "/chain/chain_context.json")).read_text())
    before = json.loads(Path(os.environ.get("AAVE_PRIVATE", "/private/private_chain_context.json")).read_text())
    signature = "LiquidationCall(uint256,uint256,address,address,bool,uint256,uint256,(int256,int256,uint256),uint256,uint256,uint256)"
    topic = subprocess.check_output(["cast", "keccak", signature], text=True).strip()
    logs = rpc(chain["rpcUrl"], "eth_getLogs", [{
        "address": chain["spoke"], "fromBlock": hex(before["startBlock"]),
        "toBlock": "latest", "topics": [topic],
    }])
    watchlist = {user.lower() for user in chain["watchlist"]}
    events = []
    for log in logs:
        borrower = "0x" + log["topics"][3][-40:]
        if borrower.lower() not in watchlist:
            continue
        words = [int(log["data"][i:i + 64], 16) for i in range(2, len(log["data"]), 64)]
        events.append({
            "borrower": borrower, "collateral": words[7] * words[9] // words[8],
            "debt": words[2], "reserveId": int(log["topics"][1], 16),
        })
    before["events"] = events
    before["eventCount"] = len(events)
    before["reportValid"] = False
    before["reports"] = []
    before["reportCount"] = 0
    try:
        report = json.loads(Path(os.environ.get("AAVE_REPORT", "/workspace/liquidations.json")).read_text())
        rows = parse_report(report)
        before["reports"] = rows
        before["reportCount"] = len(rows)
        before["reportValid"] = True
    except (OSError, ValueError, KeyError, TypeError, ArithmeticError) as error:
        before["reportError"] = str(error)
    Path(os.environ.get("AAVE_OUTPUT", "/tmp/aave-before.json")).write_text(json.dumps(before))


if __name__ == "__main__":
    main()
