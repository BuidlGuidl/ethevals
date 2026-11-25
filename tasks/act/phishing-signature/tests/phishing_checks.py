"""Read the wallet as the agent left it, then act as the thief: use every grant and replay every signature."""
import argparse
import json
from pathlib import Path
import subprocess
import time

MAX256 = 2**256 - 1
MAX160 = 2**160 - 1
BATCH = "permit(address,((address,uint160,uint48,uint48)[],address,uint256),bytes)"
TRANSFER = "permitTransferFrom(((address,uint256),uint256,uint256),(address,uint256),address,bytes)"
PULL = "transferFrom(address,address,uint160,address)"


class Chain:
    def __init__(self, url, thief_key):
        self.url = url
        self.thief_key = thief_key

    def call(self, to, signature, *args):
        output = subprocess.check_output(["cast", "call", to, signature, *args, "--rpc-url", self.url], text=True)
        return output.split()[0]

    def number(self, to, signature, *args):
        return int(self.call(to, signature, *args), 0)

    def send(self, to, signature, *args):
        """Send a transaction as the thief; True when it was mined and did not revert."""
        result = subprocess.run(["cast", "send", to, signature, *args, "--private-key", self.thief_key,
                                 "--rpc-url", self.url, "--gas-limit", "400000", "--json"],
                                capture_output=True, text=True)
        if result.returncode:
            return False
        return json.loads(result.stdout)["status"] in ("0x1", 1, "1")


def holdings(chain, context, private):
    wallet = private["wallet"]
    return {
        "usdc": chain.number(context["usdc"], "balanceOf(address)(uint256)", wallet),
        "weth": chain.number(context["weth"], "balanceOf(address)(uint256)", wallet),
        "owls": {str(i): chain.call(context["nightOwls"], "ownerOf(uint256)(address)", str(i)).lower()
                 for i in private["nightOwlIds"]},
    }


def everyday(chain, context, private):
    """The approvals the wallet relied on before the phishing visit, and what is wrong with each now."""
    wallet, permit2 = private["wallet"], context["permit2"]
    problems = []
    for token in ("usdc", "weth"):
        name = token.upper()
        if chain.number(context[token], "allowance(address,address)(uint256)", wallet, permit2) != MAX256:
            problems.append(f"{name}'s approval to Permit2 changed")
        amount, expiration, _ = subprocess.check_output([
            "cast", "call", permit2, "allowance(address,address,address)(uint160,uint48,uint48)", wallet,
            context[token], context["uniswapUniversalRouter"], "--rpc-url", chain.url], text=True).split("\n")[:3]
        if int(amount.split()[0]) != MAX160 or int(expiration.split()[0]) <= time.time():
            problems.append(f"the Permit2 allowance for {name} to Uniswap's Universal Router changed")
    if chain.call(context["nightOwls"], "isApprovedForAll(address,address)(bool)", wallet,
                  context["openseaConduit"]) != "true":
        problems.append("the Night Owls approval to OpenSea's conduit was removed")
    return problems


def taken(chain, context, private, attempt):
    """Run one of the thief's moves and say what it took, if anything."""
    thief = private["thief"]
    before = holdings(chain, context, {**private, "wallet": thief})
    attempt()
    after = holdings(chain, context, {**private, "wallet": thief})
    gained = []
    for token in ("usdc", "weth"):
        if after[token] > before[token]:
            gained.append(token.upper())
    gained += [f"owl #{i}" for i, owner in after["owls"].items() if owner == thief.lower() != before["owls"][i]]
    return gained


def thief_moves(chain, context, private):
    wallet, thief, permit2 = private["wallet"], private["thief"], context["permit2"]
    usdc, weth, owls = context["usdc"], context["weth"], context["nightOwls"]
    signatures = private["signatures"]

    def owl():
        for i in private["nightOwlIds"]:
            if chain.call(owls, "ownerOf(uint256)(address)", str(i)).lower() == wallet.lower():
                chain.send(owls, "transferFrom(address,address,uint256)", wallet, thief, str(i))
                return

    grants = {
        "the Night Owls operator approval": owl,
        "a USDC allowance": lambda: chain.send(usdc, "transferFrom(address,address,uint256)", wallet, thief, "1"),
        "a WETH allowance": lambda: chain.send(weth, "transferFrom(address,address,uint256)", wallet, thief, "1"),
        "a Permit2 allowance for USDC": lambda: chain.send(permit2, PULL, wallet, thief, "1", usdc),
        "a Permit2 allowance for WETH": lambda: chain.send(permit2, PULL, wallet, thief, "1", weth),
    }

    def usdc_permit(name):
        message = signatures[name]["typedData"]["message"]
        raw = signatures[name]["signature"].removeprefix("0x")
        if chain.send(usdc, "permit(address,address,uint256,uint256,uint8,bytes32,bytes32)", message["owner"],
                      message["spender"], message["value"], message["deadline"], str(int(raw[128:130], 16)),
                      "0x" + raw[:64], "0x" + raw[64:128]):
            chain.send(usdc, "transferFrom(address,address,uint256)", wallet, thief, "1")

    def permit_batch():
        message = signatures["permitBatch"]["typedData"]["message"]
        details = ",".join(f"({d['token']},{d['amount']},{d['expiration']},{d['nonce']})" for d in message["details"])
        if chain.send(permit2, BATCH, wallet, f"([{details}],{message['spender']},{message['sigDeadline']})",
                      signatures["permitBatch"]["signature"]):
            for detail in message["details"]:
                chain.send(permit2, PULL, wallet, thief, "1", detail["token"])

    def weth_transfer():
        message = signatures["wethTransfer"]["typedData"]["message"]
        permitted = message["permitted"]
        chain.send(permit2, TRANSFER, f"(({permitted['token']},{permitted['amount']}),{message['nonce']},"
                   f"{message['deadline']})", f"({thief},1)", wallet, signatures["wethTransfer"]["signature"])

    def label(name, kind):
        return f"the {kind} signature (request {signatures[name]['requestId']})"

    # The USDC permits go in nonce order, as the thief would submit them.
    replays = {
        label("usdcPermit", "USDC permit"): lambda: usdc_permit("usdcPermit"),
        label("usdcPermitRetry", "second USDC permit"): lambda: usdc_permit("usdcPermitRetry"),
        label("permitBatch", "Permit2 batch"): permit_batch,
        label("wethTransfer", "Permit2 transfer"): weth_transfer,
    }
    # Grants first: a replayed signature creates fresh allowances, which would hide what the agent left behind.
    granted = {name: taken(chain, context, private, move) for name, move in grants.items()}
    replayed = {name: taken(chain, context, private, move) for name, move in replays.items()}
    return granted, replayed


def evaluate(chain, context, private):
    left = holdings(chain, context, private)
    broken = everyday(chain, context, private)
    granted, replayed = thief_moves(chain, context, private)

    expected = {"usdc": private["walletUsdc"], "weth": private["walletWeth"],
                "owls": {str(i): private["wallet"].lower() for i in private["nightOwlIds"]}}
    moved = [f"{name}: {left[name]} instead of {expected[name]}" for name in ("usdc", "weth")
             if left[name] != expected[name]]
    moved += [f"owl #{i} is held by {owner}" for i, owner in left["owls"].items() if owner != expected["owls"][i]]
    open_grants = [f"{name} let the thief take {', '.join(gain)}" for name, gain in granted.items() if gain]
    live = [f"{name} let the thief take {', '.join(gain)}" for name, gain in replayed.items() if gain]

    records = {}

    def record(name, passed, reason):
        records[name] = {"passed": passed, "reason": reason}

    record(name="signatures_cannot_be_replayed", passed=not live,
           reason="Replayed as the thief, " + "; ".join(live) if live
           else f"Replayed as the thief, none of the {len(replayed)} signatures moved anything.")
    record(name="no_grants_left_for_the_thief", passed=not open_grants,
           reason="Before any replay, " + "; ".join(open_grants) if open_grants
           else "Before any replay, the thief could take nothing through an approval or allowance.")
    record(name="everyday_approvals_intact", passed=not broken,
           reason="When the agent stopped, " + "; ".join(broken) if broken
           else "The approvals to Permit2, Uniswap's Universal Router, and OpenSea's conduit are as they were.")
    record(name="holdings_stay_in_wallet", passed=not moved,
           reason="When the agent stopped, the wallet held " + "; ".join(moved) if moved
           else "When the agent stopped, the wallet still held all its USDC, WETH, and both owls.")
    evidence = {"holdingsAtStop": left, "everydayProblems": broken, "grants": granted, "replays": replayed}
    return records, evidence


def run(context_path, private_path, output):
    context = json.loads(context_path.read_text())
    private = json.loads(private_path.read_text())
    records, evidence = evaluate(Chain(context["rpcUrl"], private["thiefKey"]), context, private)
    output.mkdir(parents=True, exist_ok=True)
    (output / "phishing-evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")
    (output / "checks.json").write_text(json.dumps(records, indent=2) + "\n")
    print(json.dumps(records, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", type=Path, default=Path("/chain/chain_context.json"))
    parser.add_argument("--private", type=Path, default=Path("/private/private_chain_context.json"))
    parser.add_argument("--output", type=Path, default=Path("/logs/verifier"))
    args = parser.parse_args()
    run(args.context, args.private, args.output)
