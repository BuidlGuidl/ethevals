"""Sell the quarterly treasury amount atomically, or record why the price floor refused it."""
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import subprocess
import urllib.request

WETH = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
USDC = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
ROUTER = "0x66a9893cC07D91D95644AEDD05D03f95e1dBA8Af"
ORACLE = "0x5f4eC3Df9cbd43714FE2740f5E3616155c5b8419"
ZERO = "0x0000000000000000000000000000000000000000"
SELF = "0x0000000000000000000000000000000000000002"
TOTAL = 400 * 10**18


def cast(*args):
    return subprocess.check_output(["cast", *map(str, args)], text=True).strip()


def encode(types, *values):
    return cast("abi-encode", f"f({types})", *values)


def rpc(url, method, params):
    request = urllib.request.Request(url, json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": method, "params": params,
    }).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=120) as response:
        result = json.load(response)
    if "error" in result:
        raise RuntimeError(f"{method}: {result['error']}")
    return result["result"]


def number(value):
    return int(value, 16) if isinstance(value, str) and value.startswith("0x") else int(value)


def balances(url, owner):
    return {
        "ETH": number(rpc(url, "eth_getBalance", [owner, "latest"])),
        "USDC": int(cast("call", USDC, "balanceOf(address)(uint256)", owner, "--rpc-url", url).split()[0]),
    }


def write_sale(report):
    temporary = Path("sale.json.tmp")
    temporary.write_text(json.dumps(report, indent=2) + "\n")
    temporary.replace("sale.json")
    print(json.dumps(report, indent=2))


def finalize(url, owner, before, receipt, quarter, journal):
    if number(receipt["status"]) != 1:
        raise RuntimeError("The sale transaction reverted. The quarter remains locked for review.")
    after = balances(url, owner)
    gas = number(receipt["gasUsed"]) * number(receipt["effectiveGasPrice"])
    sold = before["ETH"] - after["ETH"] - gas
    received = after["USDC"] - before["USDC"]
    report = {
        "status": "success", "quarter": quarter,
        "ethSold": str(Decimal(sold) / 10**18),
        "usdcReceived": str(Decimal(received) / 10**6),
        "transactionHashes": [receipt["transactionHash"]],
    }
    write_sale(report)
    journal.write_text(json.dumps({"status": "success", **report}) + "\n")


def main():
    context = json.loads(Path("chain_context.json").read_text())
    url, key = context["rpcUrl"], context["privateKey"]
    if number(rpc(url, "eth_chainId", [])) != 1 or number(context["chainId"]) != 1:
        raise RuntimeError("This route requires Ethereum mainnet addresses.")
    owner = cast("wallet", "address", "--private-key", key)
    block = rpc(url, "eth_getBlockByNumber", ["latest", False])
    date = datetime.fromtimestamp(number(block["timestamp"]), tz=timezone.utc)
    quarter = f"{date.year}-Q{(date.month - 1) // 3 + 1}"
    journal = Path(f"sale-{quarter}.journal.json")
    if journal.exists():
        prior = json.loads(journal.read_text())
        if prior["status"] == "success":
            print(f"A sale already completed for {quarter}; no second sale sent.")
            return
        # A crash after submission can leave an unknown hash. Keep the lock for manual review.
        raise RuntimeError("An earlier sale is pending or interrupted. Check its receipt before any new sale.")

    before = balances(url, owner)
    if before["ETH"] < TOTAL + 10**17:
        raise RuntimeError("The wallet needs 400 ETH and a gas reserve.")
    answer = int(cast("call", ORACLE, "latestAnswer()(int256)", "--rpc-url", url).split()[0])
    if answer <= 0:
        raise RuntimeError("Chainlink returned no positive reference price.")
    # USDC uses 6 decimals; the Chainlink answer uses 8 and ETH uses 18.
    minimum = (TOTAL * answer * 985 + 1000 * 10**20 - 1) // (1000 * 10**20)

    inputs = [encode("address,uint256", SELF, 250 * 10**18)]
    v4_swap = encode("((address,address,uint24,int24,address),bool,uint128,uint128,bytes)",
                     f"(({ZERO},{USDC},3000,60,{ZERO}),true,{150 * 10**18},0,0x)")
    v4_settle = encode("address,uint256", ZERO, 150 * 10**18)
    v4_take = encode("address,uint256", USDC, 0)
    inputs.append(encode("bytes,bytes[]", "0x060c0f", f"[{v4_swap},{v4_settle},{v4_take}]"))
    path = "0x" + WETH[2:] + "000064" + USDC[2:]
    inputs.append(encode("address,uint256,uint256,bytes,bool", owner, 190 * 10**18, 0, path, "false"))
    inputs.append(encode("address,uint256,uint256,address[],bool", owner, 60 * 10**18, 0,
                         f"[{WETH},{USDC}]", "false"))
    inputs.append(encode("address,uint256", owner, 0))  # Unwrap any unused WETH.
    inputs.append(encode("address,address,uint256", ZERO, owner, 0))  # Refund unused native ETH.
    inputs.append(encode("address,address,uint256", owner, USDC, before["USDC"] + minimum))
    data = cast("calldata", "execute(bytes,bytes[],uint256)", "0x0b1000080c040e",
                "[" + ",".join(inputs) + "]", number(block["timestamp"]) + 600)
    transaction = {"from": owner, "to": ROUTER, "value": hex(TOTAL), "data": data}
    try:
        rpc(url, "eth_call", [transaction, "latest"])
    except RuntimeError:
        write_sale({"status": "refused", "quarter": quarter, "ethSold": "0", "usdcReceived": "0",
                    "transactionHashes": [], "reason": "The atomic route cannot meet the 98.5% Chainlink floor."})
        return
    # Reserve the quarter before submission so a crash cannot cause another 400 ETH sale.
    with journal.open("x") as lock:
        json.dump({"status": "pending", "quarter": quarter, "before": before}, lock)
    receipt = json.loads(cast("send", ROUTER, data, "--value", TOTAL,
                              "--rpc-url", url, "--private-key", key, "--json"))
    finalize(url, owner, before, receipt, quarter, journal)


if __name__ == "__main__":
    main()
