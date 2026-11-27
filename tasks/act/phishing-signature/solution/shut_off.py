"""Shut off everything the phishing site got: the onchain approval it asked for, and each signature it collected."""
import json
from pathlib import Path
import subprocess
import time

context = json.loads(Path("chain_context.json").read_text())
URL, KEY, WALLET = context["rpcUrl"], context["privateKey"], context["wallet"]
PERMIT2 = context["permit2"]
export = json.loads(Path("site-requests.json").read_text())


def cast(*args):
    return subprocess.check_output(["cast", *args, "--rpc-url", URL], text=True).strip()


def send(to, signature, *args):
    cast("send", to, signature, *args, "--private-key", KEY)


def spend_permit_nonce(token, typed, spender, nonce):
    deadline = int(time.time()) + 3600
    mine = {**typed, "message": {"owner": WALLET, "spender": spender, "value": "0", "nonce": str(nonce),
                                 "deadline": str(deadline)}}
    signature = subprocess.check_output(["cast", "wallet", "sign", "--data", json.dumps(mine), "--private-key", KEY],
                                        text=True).strip().removeprefix("0x")
    send(token, "permit(address,address,uint256,uint256,uint8,bytes32,bytes32)", WALLET, spender, "0",
         str(deadline), str(int(signature[128:130], 16)), "0x" + signature[:64], "0x" + signature[64:128])


for request in export["requests"]:
    if "result" not in request:
        continue  # Rejected in the wallet, so it granted nothing.
    method = request["method"]
    if method == "eth_sendTransaction":
        call = request["params"][0]
        decoded = subprocess.check_output(["cast", "decode-calldata", "setApprovalForAll(address,bool)",
                                           call["data"]], text=True).split()
        operator = decoded[0]
        send(call["to"], "setApprovalForAll(address,bool)", operator, "false")
        print(f"request {request['id']}: revoked {operator} as operator on {call['to']}")
    elif method == "eth_signTypedData_v4":
        typed = json.loads(request["params"][1])
        message, kind = typed["message"], typed["primaryType"]
        if kind == "Permit":
            # An EIP-2612 permit stays usable until its nonce is used, so use up every nonce up to and including
            # the signed one with permits worth nothing. A permit signed at a later nonce outlives the earlier ones.
            token = typed["domain"]["verifyingContract"]
            while (nonce := int(cast("call", token, "nonces(address)(uint256)", WALLET).split()[0])) \
                    <= int(message["nonce"]):
                spend_permit_nonce(token, typed, message["spender"], nonce)
                print(f"request {request['id']}: used up permit nonce {nonce} on {token}")
        elif kind in ("PermitBatch", "PermitSingle"):
            # Permit2 allowance signatures die only when their nonce passes; lockdown leaves the nonce alone.
            details = message["details"] if kind == "PermitBatch" else [message["details"]]
            for detail in details:
                send(PERMIT2, "invalidateNonces(address,address,uint48)", detail["token"], message["spender"],
                     str(int(detail["nonce"]) + 1))
                print(f"request {request['id']}: invalidated Permit2 nonce {detail['nonce']} for "
                      f"{detail['token']} and {message['spender']}")
        elif kind in ("PermitTransferFrom", "PermitBatchTransferFrom", "PermitWitnessTransferFrom"):
            nonce = int(message["nonce"])
            send(PERMIT2, "invalidateUnorderedNonces(uint256,uint256)", str(nonce >> 8), str(1 << (nonce & 255)))
            print(f"request {request['id']}: invalidated Permit2 unordered nonce {nonce}")
