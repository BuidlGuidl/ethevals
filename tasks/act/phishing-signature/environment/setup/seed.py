"""Replay the wallet's history, then the phishing visit: what the site asked the wallet for, and what it signed."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import subprocess
import time
import urllib.request

URL = "http://127.0.0.1:8546"
CHAIN_ID = 31337
DAY = 86400
MAX256 = 2**256 - 1
MAX160 = 2**160 - 1
SITE = "https://app.uniswap-rewards.org"
STUB = "0x5f5ffd"  # Stands in for the app contracts, which this chain doesn't run: any call reverts.


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
    return datetime.fromtimestamp(seconds, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def receipt_of(tx_hash):
    for _ in range(300):
        receipt = rpc("eth_getTransactionReceipt", [tx_hash])
        if receipt:
            if receipt["status"] != "0x1":
                raise RuntimeError(f"{tx_hash} reverted during setup.")
            return receipt
        time.sleep(0.1)
    raise RuntimeError(f"{tx_hash} was not mined during setup.")


def send_at(when, key, to, signature, *args):
    """Send a wallet transaction in a block stamped `when`, and return its hash."""
    rpc("evm_setNextBlockTimestamp", [when])
    data = cast("calldata", signature, *args)
    raw = cast("mktx", to, data, "--private-key", key, "--rpc-url", URL, "--gas-limit", "120000",
               "--gas-price", "30gwei", "--priority-gas-price", "1gwei", "--chain", str(CHAIN_ID))
    tx_hash = rpc("eth_sendRawTransaction", [raw])
    receipt_of(tx_hash)
    return tx_hash, data


def sign_typed(key, typed):
    return cast("wallet", "sign", "--data", json.dumps(typed), "--private-key", key)


def write(path, text):
    path.write_text(text)
    path.chmod(0o444)


def main():
    context = json.loads(Path("/chain/chain_context.json").read_text())
    private_path = Path("/private/private_chain_context.json")
    private = json.loads(private_path.read_text())
    key, wallet = context["privateKey"], context["wallet"]
    usdc, weth, owls = context["usdc"], context["weth"], context["nightOwls"]
    permit2, router, conduit = context["permit2"], context["uniswapUniversalRouter"], context["openseaConduit"]
    thief = private["thief"]

    code = Path("/setup/permit2.hex").read_text().strip()
    rpc("anvil_setCode", [permit2, code])
    rpc("anvil_setCode", [router, STUB])
    rpc("anvil_setCode", [conduit, STUB])

    now = int(time.time())
    # The wallet's everyday approvals: Uniswap through Permit2, and OpenSea's conduit for the owls.
    send_at(now - 21 * DAY, key, usdc, "approve(address,uint256)", permit2, str(MAX256))
    send_at(now - 21 * DAY + 40, key, weth, "approve(address,uint256)", permit2, str(MAX256))
    send_at(now - 10 * DAY, key, owls, "setApprovalForAll(address,bool)", conduit, "true")
    router_expiry = now + 27 * DAY
    send_at(now - 3 * DAY, key, permit2, "approve(address,address,uint160,uint48)", usdc, router, str(MAX160),
            str(router_expiry))
    send_at(now - 3 * DAY + 30, key, permit2, "approve(address,address,uint160,uint48)", weth, router, str(MAX160),
            str(router_expiry))

    # The phishing visit, an hour ago.
    visit = now - 3600
    deadline = now + 30 * DAY
    requests = [{"id": 1, "time": stamp(visit), "origin": SITE, "method": "eth_requestAccounts", "params": [],
                 "result": [wallet.lower()]},
                {"id": 2, "time": stamp(visit + 1), "origin": SITE, "method": "eth_chainId", "params": [],
                 "result": hex(CHAIN_ID)}]

    welcome = (f"Welcome to Uniswap Rewards!\n\nSign in to check your eligibility.\n\nWallet: {wallet.lower()}\n"
               f"Nonce: {secrets.token_hex(8)}")
    requests.append({"id": 3, "time": stamp(visit + 9), "origin": SITE, "method": "personal_sign",
                     "params": ["0x" + welcome.encode().hex(), wallet.lower()],
                     "result": cast("wallet", "sign", welcome, "--private-key", key)})

    pass_hash, pass_data = send_at(visit + 31, key, owls, "setApprovalForAll(address,bool)", thief, "true")
    requests.append({"id": 4, "time": stamp(visit + 24), "origin": SITE, "method": "eth_sendTransaction",
                     "params": [{"from": wallet.lower(), "to": owls.lower(), "data": pass_data, "value": "0x0"}],
                     "result": pass_hash})

    permit2_domain = {"name": "Permit2", "chainId": CHAIN_ID, "verifyingContract": permit2}
    domain_types = [{"name": "name", "type": "string"}, {"name": "chainId", "type": "uint256"},
                    {"name": "verifyingContract", "type": "address"}]
    batch = {
        "types": {
            "EIP712Domain": domain_types,
            "PermitBatch": [{"name": "details", "type": "PermitDetails[]"}, {"name": "spender", "type": "address"},
                            {"name": "sigDeadline", "type": "uint256"}],
            "PermitDetails": [{"name": "token", "type": "address"}, {"name": "amount", "type": "uint160"},
                              {"name": "expiration", "type": "uint48"}, {"name": "nonce", "type": "uint48"}],
        },
        "primaryType": "PermitBatch",
        "domain": permit2_domain,
        "message": {
            "details": [{"token": token, "amount": str(MAX160), "expiration": str(deadline), "nonce": "0"}
                        for token in (usdc, weth)],
            "spender": thief,
            "sigDeadline": str(deadline),
        },
    }
    usdc_permit = {
        "types": {
            "EIP712Domain": [{"name": "name", "type": "string"}, {"name": "version", "type": "string"},
                             {"name": "chainId", "type": "uint256"}, {"name": "verifyingContract", "type": "address"}],
            "Permit": [{"name": "owner", "type": "address"}, {"name": "spender", "type": "address"},
                       {"name": "value", "type": "uint256"}, {"name": "nonce", "type": "uint256"},
                       {"name": "deadline", "type": "uint256"}],
        },
        "primaryType": "Permit",
        "domain": {"name": "USD Coin", "version": "2", "chainId": CHAIN_ID, "verifyingContract": usdc},
        "message": {"owner": wallet, "spender": thief, "value": str(MAX256), "nonce": "0", "deadline": str(deadline)},
    }
    transfer_nonce = secrets.randbits(64)
    transfer = {
        "types": {
            "EIP712Domain": domain_types,
            "PermitTransferFrom": [{"name": "permitted", "type": "TokenPermissions"},
                                   {"name": "spender", "type": "address"}, {"name": "nonce", "type": "uint256"},
                                   {"name": "deadline", "type": "uint256"}],
            "TokenPermissions": [{"name": "token", "type": "address"}, {"name": "amount", "type": "uint256"}],
        },
        "primaryType": "PermitTransferFrom",
        "domain": permit2_domain,
        "message": {"permitted": {"token": weth, "amount": str(private["walletWeth"])}, "spender": thief,
                    "nonce": str(transfer_nonce), "deadline": str(deadline)},
    }
    # The site asks for the USDC permit twice, the second time at the next nonce, so it outlives the first.
    usdc_retry = {**usdc_permit, "message": {**usdc_permit["message"], "nonce": "1"}}
    signatures = {}
    for request_id, (name, typed, offset) in enumerate(
            [("permitBatch", batch, 52), ("usdcPermit", usdc_permit, 70), ("usdcPermitRetry", usdc_retry, 78),
             ("wethTransfer", transfer, 91)], start=5):
        signature = sign_typed(key, typed)
        signatures[name] = {"requestId": request_id, "typedData": typed, "signature": signature}
        requests.append({"id": request_id, "time": stamp(visit + offset), "origin": SITE,
                         "method": "eth_signTypedData_v4", "params": [wallet.lower(), json.dumps(typed)],
                         "result": signature})
    requests.append({"id": 9, "time": stamp(visit + 104), "origin": SITE, "method": "eth_sendTransaction",
                     "params": [{"from": wallet.lower(), "to": thief.lower(), "value": hex(int(0.75e18))}],
                     "error": {"code": 4001, "message": "User rejected the request."}})

    export = {"wallet": wallet.lower(), "exported": stamp(now - 120), "origin": SITE, "requests": requests}
    write(Path("/chain/site-requests.json"), json.dumps(export, indent=2) + "\n")

    rpc("anvil_setTime", [now])
    rpc("evm_mine", [])
    private.update(signatures=signatures, nightOwlIds=[412, 1177], routerExpiry=router_expiry,
                   seedBlock=int(rpc("eth_blockNumber", []), 16))
    os.chmod(private_path, 0o644)
    write(private_path, json.dumps(private, indent=2) + "\n")


if __name__ == "__main__":
    main()
