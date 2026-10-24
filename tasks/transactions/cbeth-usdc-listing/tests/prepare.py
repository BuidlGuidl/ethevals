"""Read the listing report into Forge's private context."""

import json
import os
import re
from decimal import Decimal
from pathlib import Path


def field(row, *names):
    if not isinstance(row, dict):
        raise ValueError("Report fields must be in an object")
    normalized = {re.sub(r"[^a-z0-9]", "", key.lower()): value for key, value in row.items()}
    for name in names:
        if name in normalized:
            return normalized[name]
    for value in row.values():
        if isinstance(value, dict):
            try:
                return field(value, *names)
            except ValueError:
                pass
    raise ValueError(f"Missing report field: {names[0]}")


def price_field(row):
    """Find a price under any key that names one, preferring USD and avoiding raw oracle scale."""
    rows, found = [row], []
    while rows:
        current = rows.pop(0)
        for key, value in current.items():
            name = re.sub(r"[^a-z0-9]", "", key.lower())
            if "price" in name and not any(word in name for word in ("raw", "scale", "wad", "e36", "1e")):
                found.append((0 if "usd" in name else 1, value))
            if isinstance(value, dict):
                rows.append(value)
    if not found:
        raise ValueError("Missing report field: price")
    return min(found, key=lambda item: item[0])[1]


def hex_value(value, size):
    if isinstance(value, dict):
        value = field(value, "address", "id", "value")
    text = str(value).strip().removeprefix("0x").removeprefix("0X")
    if not re.fullmatch(rf"[0-9a-fA-F]{{{size}}}", text):
        raise ValueError("Report id or address has the wrong length")
    return "0x" + text.lower()


def parse_report(report):
    market = field(report, "marketid", "morphomarketid", "marketidentifier", "id", "market")
    oracle = field(report, "oracleaddress", "oracleaddr", "oracle", "priceoracle", "oraclecontract")
    try:
        price = field(report, "pricepercbethinusdc", "pricepercbethusdc", "priceusdcpercbeth", "cbethpriceusdc", "priceusdc",
                      "cbethpriceinusdc", "priceinusdc", "usdcpercbeth", "cbethprice", "pricepercbeth", "priceper1cbeth",
                      "oraclepriceusdc", "price", "oracleprice")
    except ValueError:
        price = price_field(report)
    if isinstance(price, dict):
        price = field(price, "usdc", "amount", "value", "price")
    text = str(price).strip().replace(",", "").removeprefix("$")
    match = re.fullmatch(r"([+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)(?:\s*USDC?(?:\s*(?:/|per)\s*(?:1\s*)?cbETH)?)?", text, re.I)
    if not match:
        raise ValueError("Report price must be a number with optional USDC units")
    amount = Decimal(match[1])
    if not amount.is_finite() or amount <= 0 or amount >= Decimal(2) ** 200:
        raise ValueError("Report price is outside the supported range")
    return {"reportMarket": hex_value(market, 64), "reportOracle": hex_value(oracle, 40),
            "reportPriceMicro": str(int(amount * 10**6)), "reportValid": True}


def main():
    before = json.loads(Path(os.environ.get("LISTING_PRIVATE", "/private/private_chain_context.json")).read_text())
    before.update(reportValid=False, reportMarket="0x" + "00" * 32,
                  reportOracle="0x" + "00" * 20, reportPriceMicro="0")
    try:
        report = json.loads(Path(os.environ.get("LISTING_REPORT", "/workspace/listing.json")).read_text())
        before.update(parse_report(report))
    except (OSError, ValueError, TypeError, ArithmeticError) as error:
        before["reportError"] = str(error)
    Path(os.environ.get("LISTING_OUTPUT", "/tmp/listing-before.json")).write_text(json.dumps(before))


if __name__ == "__main__":
    main()
