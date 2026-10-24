"""Copy the report and chain events into Forge's private input file."""

import json
import os
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


def field(row, *names):
    for name in names:
        if name in row:
            return row[name]
    raise ValueError(f"Missing report field: {names[0]}")


def amounts(value, decimals):
    number = Decimal(str(value))
    if not number.is_finite() or number < 0:
        raise ValueError("Report amounts must be finite and nonnegative")
    return int(number), int(number * 10**decimals)


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
        if isinstance(report, dict):
            report = report["liquidations"]
        if not isinstance(report, list):
            raise ValueError("The report must contain a list of liquidations")
        tokens = {
            "weth": (0, 18), "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2": (0, 18),
            "wbtc": (3, 8), "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599": (3, 8),
        }
        rows = []
        for row in report:
            borrower = field(row, "borrower", "user")
            debt = field(row, "debtRepaidUSDC", "debt_repaid_usdc", "debtRepaid", "debt_repaid")
            collateral = field(row, "collateralSeized", "collateral_seized", "collateral")
            if isinstance(collateral, dict):
                token = field(collateral, "token", "asset", "symbol")
                amount = field(collateral, "amount", "amountSeized", "amount_seized")
            else:
                token = field(row, "collateralToken", "collateral_token", "token")
                amount = collateral
            reserve, decimals = tokens[str(token).lower()]
            raw_debt, human_debt = amounts(debt, 6)
            raw_collateral, human_collateral = amounts(amount, decimals)
            rows.append({
                "borrower": borrower, "collateralHuman": human_collateral, "collateralRaw": raw_collateral,
                "debtHuman": human_debt, "debtRaw": raw_debt, "reserveId": reserve,
            })
        before["reports"] = rows
        before["reportCount"] = len(rows)
        before["reportValid"] = True
    except (OSError, ValueError, KeyError, TypeError, ArithmeticError) as error:
        before["reportError"] = str(error)
    Path(os.environ.get("AAVE_OUTPUT", "/tmp/aave-before.json")).write_text(json.dumps(before))


if __name__ == "__main__":
    main()
