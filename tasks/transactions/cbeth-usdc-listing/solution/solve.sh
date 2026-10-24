#!/bin/sh
set -eu
cd /workspace
test -r chain_context.json
test ! -r /private/private_chain_context.json
python3 - <<'PY'
import json
import secrets
import subprocess
from decimal import Decimal
from pathlib import Path

chain = json.loads(Path("chain_context.json").read_text())
rpc = chain["rpcUrl"]
key = chain["privateKey"]
morpho = chain["morpho"]
factory = "0x3A7bB36Ee3f3eE32A60e9f2b33c1e5f2E83ad766"
irm = "0x870aC11D48B15DB9a138Cf899d20F13F79Ba00BC"
cbeth_eth = "0xF017fcB346A1885194689bA23Eff2fE6fA5C483b"
eth_usd = "0x5f4eC3Df9cbd43714FE2740f5E3616155c5b8419"
usdc_usd = "0x8fFfFfd4AfB6115b954Bd326cbe7B4BA576818f6"
zero = "0x" + "00" * 20


def cast(*args):
    return subprocess.check_output(["cast", *map(str, args)], text=True).strip()


def call(target, signature, *args):
    return json.loads(cast("call", target, signature, *args, "--rpc-url", rpc, "--json"))


def send(target, signature, *args):
    estimate = int(cast("estimate", target, signature, *args, "--from", chain["wallet"], "--rpc-url", rpc))
    receipt = json.loads(cast("send", target, signature, *args, "--private-key", key,
                              "--rpc-url", rpc, "--gas-limit", estimate * 3 // 2, "--json"))
    if int(receipt["status"], 16) != 1:
        raise RuntimeError(f"Transaction failed: {receipt['transactionHash']}")
    return receipt


signature = "createMorphoChainlinkOracleV2(address,uint256,address,address,uint256,address,uint256,address,address,uint256,bytes32)"
receipt = send(factory, signature, zero, 1, cbeth_eth, eth_usd, 18, zero, 1, usdc_usd, zero, 6,
               "0x" + secrets.token_hex(32))
topic = cast("keccak", "CreateMorphoChainlinkOracleV2(address,address)").lower()
event = next(log for log in receipt["logs"] if log["address"].lower() == factory.lower()
             and log["topics"][0].lower() == topic)
oracle = "0x" + event["data"][-40:]
price = int(call(oracle, "price()(uint256)")[0])
rate = int(call(chain["cbeth"], "exchangeRate()(uint256)")[0])
eth_answer = int(call(eth_usd, "latestRoundData()(uint80,int256,uint256,uint256,uint80)")[1])
usdc_answer = int(call(usdc_usd, "latestRoundData()(uint80,int256,uint256,uint256,uint80)")[1])
reference = rate * eth_answer * 10**6 // usdc_answer
if abs(price - reference) * 100 > reference * 2:
    raise RuntimeError("Deployed oracle price differs from the exchange-rate reference by more than 2%")
params = f"({chain['usdc']},{chain['cbeth']},{oracle},{irm},860000000000000000)"
encoded = cast("abi-encode", "f((address,address,address,address,uint256))", params)
market_id = cast("keccak", encoded)
send(morpho, "createMarket((address,address,address,address,uint256))", params)
send(chain["usdc"], "approve(address,uint256)", morpho, 2_000_000 * 10**6)
send(morpho, "supply((address,address,address,address,uint256),uint256,uint256,address,bytes)",
     params, 2_000_000 * 10**6, 0, chain["wallet"], "0x")
shares = int(call(morpho, "position(bytes32,address)(uint256,uint128,uint128)", market_id, chain["wallet"])[0])
if shares <= 0:
    raise RuntimeError("Wallet has no market supply after seeding")
price = int(call(oracle, "price()(uint256)")[0])
Path("listing.json").write_text(json.dumps({"marketId": market_id, "oracleAddress": oracle,
    "pricePerCbethInUSDC": str(Decimal(price) / Decimal(10**24))}, indent=2) + "\n")
print(f"Seeded {market_id}; oracle returns {price}, or {Decimal(price) / Decimal(10**24)} USDC per cbETH.")
PY
