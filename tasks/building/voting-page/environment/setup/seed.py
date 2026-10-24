"""Deploy the unchanged contracts and prepare a block-based governance history."""
import argparse
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import subprocess
import time
import urllib.request

UNIT = 10**18
STATES = ("Pending", "Active", "Canceled", "Defeated", "Succeeded", "Queued", "Expired", "Executed")
DESCRIPTIONS = {
    "defeated": "Set the protocol fee to 11 basis points",
    "succeeded": "Set the protocol fee to 12 basis points",
    "queued_waiting": "Set the protocol fee to 13 basis points",
    "queued_ready": "Set the protocol fee to 14 basis points",
    "executed": "Set the protocol fee to 15 basis points",
    "extended": "Set the protocol fee to 16 basis points",
    "twin": "Set the protocol fee to 17 basis points",
    "for_abstain": "Set the protocol fee to 18 basis points",
    "pending": "Set the protocol fee to 19 basis points",
}
HISTORY = {
    "history_executed": "Set the protocol fee to 6 basis points",
    "history_defeated": "Set the protocol fee to 7 basis points",
    "history_queued": "Set the protocol fee to 8 basis points",
    "history_active": "Set the protocol fee to 9 basis points",
    "history_pending": "Set the protocol fee to 10 basis points",
}


def command(*args, cwd=None):
    result = subprocess.run(args, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        # Commands can include private keys. Never include their arguments in an error.
        raise RuntimeError(f"{args[0]} failed: {result.stderr[-3000:]}")
    return result.stdout.strip()


def rpc(url, method, params=None):
    body = json.dumps(dict(jsonrpc="2.0", id=1, method=method, params=params or [])).encode()
    request = urllib.request.Request(url, body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=60) as response:
        result = json.load(response)
    if "error" in result:
        raise RuntimeError(f"{method}: {result['error']}")
    return result["result"]


@lru_cache(maxsize=None)
def calldata(signature, *args):
    return command("cast", "calldata", signature, *map(str, args))


def words(data):
    return [int(data[i:i + 64], 16) for i in range(2, len(data), 64)]


def read(url, to, signature, *args):
    return words(rpc(url, "eth_call", [{"to": to, "data": calldata(signature, *args)}, "latest"]))


def receipt(url, tx):
    for _ in range(300):
        value = rpc(url, "eth_getTransactionReceipt", [tx])
        if value:
            if int(value["status"], 16) != 1:
                raise RuntimeError(f"Transaction reverted: {tx}")
            return value
        time.sleep(0.1)
    raise TimeoutError(f"Transaction did not mine: {tx}")


def send(url, key, to, signature, *args, wait=True, value=0, nonce=None):
    options = ["--rpc-url", url, "--private-key", key, "--gas-limit", "6000000", "--gas-price", "2000000000", "--async"]
    if nonce is not None:
        options += ["--nonce", str(nonce)]
    if value:
        options += ["--value", str(value)]
    transaction = command("cast", "send", to, calldata(signature, *args) if signature else "0x", *options)
    return receipt(url, transaction) if wait else transaction


def mine_to(url, number):
    current = int(rpc(url, "eth_blockNumber"), 16)
    while number > current:
        count = min(1_000, number - current)
        rpc(url, "anvil_mine", [hex(count), "0xc"])
        current += count


def write_json(path, value, mode):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.chmod(0o600)
    path.write_text(json.dumps(value, indent=2) + "\n")
    path.chmod(mode)


def deploy(url, root, private, key):
    addresses = {}
    for name in ("Token", "Protocol"):
        output = command("forge", "create", f"src/{name}.sol:{name}", "--broadcast", "--json",
                         "--private-key", key, "--rpc-url", url, cwd=root)
        addresses[name] = json.loads(output)["deployedTo"]
    output = command("forge", "script", "script/Deploy.s.sol:Deploy", "--sig", "run(address)", addresses["Token"],
                     "--private-key", key, "--sender", command("cast", "wallet", "address", "--private-key", key),
                     "--broadcast", "--slow", "--non-interactive", "--rpc-url", url, cwd=root)
    # The script output and broadcast files remain only in the chain sidecar or the local kit.
    (private / "deploy.log").write_text(output + "\n")
    transactions = json.loads((root / "broadcast/Deploy.s.sol/31337/run-latest.json").read_text())["transactions"]
    for tx in transactions:
        if tx["transactionType"] == "CREATE":
            addresses[tx["contractName"]] = tx["contractAddress"]
    return addresses


def seed(url, root, public, private):
    started = time.monotonic()
    if int(rpc(url, "eth_chainId"), 16) != 31337 or int(rpc(url, "eth_blockNumber"), 16) > 2:
        raise RuntimeError("Seeding requires a fresh local chain 31337.")
    private.mkdir(parents=True, exist_ok=True)
    private.chmod(0o700)
    rpc(url, "anvil_setBlockTimestampInterval", [12])
    accounts = []
    for index in range(5):
        key = "0x" + hashlib.sha256(f"voting-page-local-chain-v1:{index}".encode()).hexdigest()
        address = command("cast", "wallet", "address", "--private-key", key)
        rpc(url, "anvil_setBalance", [address, hex(1000 * UNIT)])
        accounts.append(dict(address=address, key=key))
    deployer, *holders = accounts
    addresses = deploy(url, root, private, deployer["key"])
    token, votes = addresses["Token"], addresses["VoteToken"]
    governor, timelock, protocol = addresses["TokenGovernor"], addresses["TimelockController"], addresses["Protocol"]
    send(url, deployer["key"], protocol, "transferOwnership(address)", timelock)
    send(url, deployer["key"], timelock, None, value=10 * UNIT)
    for holder, amount in zip(holders, (3_000_000, 2_000_000, 4_500_000, 2_500_000), strict=True):
        send(url, deployer["key"], token, "transfer(address,uint256)", holder["address"], amount * UNIT)
        send(url, holder["key"], token, "approve(address,uint256)", votes, amount * UNIT)
        send(url, holder["key"], votes, "depositFor(address,uint256)", holder["address"], amount * UNIT)
        send(url, holder["key"], votes, "delegate(address)", holder["address"])

    context = dict(rpcUrl="http://chain:8545", chainId=31337, token=token, voteToken=votes, governor=governor, timelock=timelock)
    private_context = dict(deployer=deployer, holders=holders, protocol=protocol, proposals={})
    seed_proposals(url, context, private_context, checks=False)
    private_context["setupBlock"] = int(rpc(url, "eth_blockNumber"), 16)
    write_json(public / "chain_context.json", context, 0o444)
    write_json(private / "private_chain_context.json", private_context, 0o400)
    print(f"Governance setup finished in {time.monotonic() - started:.1f}s at block {private_context['setupBlock']}", flush=True)


def seed_proposals(url, context, private, *, checks):
    deployer, holders = private["deployer"], private["holders"]
    governor, protocol = context["governor"], private["protocol"]
    proposals = private["proposals"]
    descriptions = DESCRIPTIONS if checks else HISTORY
    if proposals.keys() & descriptions.keys():
        raise RuntimeError("These proposals already exist in private context. Start from the chain before this step.")

    def batch(names):
        nonce = int(rpc(url, "eth_getTransactionCount", [deployer["address"], "pending"]), 16)
        rpc(url, "evm_setAutomine", [False])
        transactions = []
        try:
            for offset, name in enumerate(names):
                fee = (11 if checks else 6) + list(descriptions).index(name)
                action = calldata("setFee(uint256)", fee)
                description = descriptions[name]
                description_hash = command("cast", "keccak", description)
                targets, values, calls = f"[{protocol}]", "[0]", f"[{action}]"
                proposal_id = read(url, governor, "hashProposal(address[],uint256[],bytes[],bytes32)",
                                   targets, values, calls, description_hash)[0]
                transaction = send(url, deployer["key"], governor, "propose(address[],uint256[],bytes[],string)",
                                   targets, values, calls, description, wait=False, nonce=nonce + offset)
                transactions.append(transaction)
                proposals[name] = dict(id=str(proposal_id), description=description, targets=[protocol], values=[0],
                                       calldatas=[action], descriptionHash=description_hash)
            rpc(url, "anvil_mine", ["0x1", "0xc"])
        finally:
            rpc(url, "evm_setAutomine", [True])
        for name, transaction in zip(names, transactions, strict=True):
            proposals[name]["createdBlock"] = int(receipt(url, transaction)["blockNumber"], 16)
            proposals[name]["snapshot"] = read(url, governor, "proposalSnapshot(uint256)", proposals[name]["id"])[0]
            proposals[name]["originalDeadline"] = read(url, governor, "proposalDeadline(uint256)", proposals[name]["id"])[0]

    def vote(name, holder, support):
        send(url, holder["key"], governor, "castVote(uint256,uint8)", proposals[name]["id"], support)

    def action(name, method):
        proposal = proposals[name]
        send(url, deployer["key"], governor, f"{method}(address[],uint256[],bytes[],bytes32)",
             f"[{protocol}]", "[0]", f"[{proposal['calldatas'][0]}]", proposal["descriptionHash"])

    if not checks:
        batch(["history_executed", "history_defeated", "history_queued"])
        mine_to(url, proposals["history_executed"]["snapshot"] + 1)
        for name in ("history_executed", "history_queued"):
            vote(name, holders[2], 1)
        vote("history_defeated", holders[0], 1)
        vote("history_defeated", holders[2], 0)
        mine_to(url, proposals["history_executed"]["originalDeadline"] + 1)
        action("history_executed", "queue")
        mine_to(url, int(rpc(url, "eth_blockNumber"), 16) + 14_401)
        action("history_executed", "execute")
        votes = context["voteToken"]
        send(url, holders[3]["key"], votes, "transfer(address,uint256)", holders[0]["address"], 2_000_000 * UNIT)
        batch(["history_active"])
        mine_to(url, proposals["history_active"]["snapshot"] + 1)
        vote("history_active", holders[1], 1)
        vote("history_active", holders[3], 0)
        send(url, holders[0]["key"], votes, "transfer(address,uint256)", holders[3]["address"], 2_000_000 * UNIT)
        action("history_queued", "queue")
        batch(["history_pending"])
        return

    batch(["defeated", "succeeded", "queued_waiting", "queued_ready", "executed"])
    mine_to(url, proposals["defeated"]["snapshot"] + 1)
    vote("defeated", holders[0], 1)
    vote("defeated", holders[1], 0)
    for name in ("succeeded", "queued_waiting", "queued_ready", "executed"):
        vote(name, holders[2], 1)
    mine_to(url, proposals["defeated"]["originalDeadline"] + 1)
    action("queued_ready", "queue")
    action("executed", "queue")
    mine_to(url, int(rpc(url, "eth_blockNumber"), 16) + 14_401)
    action("executed", "execute")

    batch(["extended", "twin"])
    original_end = proposals["extended"]["originalDeadline"]
    mine_to(url, proposals["extended"]["snapshot"] + 1)
    vote("twin", holders[0], 1)
    mine_to(url, original_end - 10_000)
    batch(["for_abstain"])
    mine_to(url, original_end - 1_000)
    vote("extended", holders[2], 1)
    vote("for_abstain", holders[0], 1)
    vote("for_abstain", holders[1], 2)
    mine_to(url, original_end - 55)
    action("queued_waiting", "queue")
    batch(["pending"])


def checks(url, public, private):
    context = json.loads((public / "chain_context.json").read_text())
    private_file = private / "private_chain_context.json"
    private_context = json.loads(private_file.read_text())
    if int(rpc(url, "eth_chainId"), 16) != context["chainId"]:
        raise RuntimeError("The chain ID differs from chain context.")
    rpc(url, "anvil_setBlockTimestampInterval", [12])
    seed_proposals(url, context, private_context, checks=True)
    private_context["checksBlock"] = int(rpc(url, "eth_blockNumber"), 16)
    write_json(private_file, private_context, 0o400)
    print(f"Governance checks prepared at block {private_context['checksBlock']}", flush=True)


def states(url, private_file, public_file=None):
    private = json.loads(private_file.read_text())
    # Keep the public context alongside the private context on the Mac and in Docker.
    public_file = public_file or private_file.parent.parent / "chain/chain_context.json"
    context = json.loads(public_file.read_text())
    governor = context["governor"]
    print("name | id | description | state | created | snapshot | deadline | For | Against | Abstain | quorum | ETA | ready", flush=True)
    for name, proposal in private["proposals"].items():
        proposal_id = proposal["id"]
        state = STATES[read(url, governor, "state(uint256)", proposal_id)[0]]
        snapshot = read(url, governor, "proposalSnapshot(uint256)", proposal_id)[0]
        deadline = read(url, governor, "proposalDeadline(uint256)", proposal_id)[0]
        against, for_votes, abstain = read(url, governor, "proposalVotes(uint256)", proposal_id)
        quorum = read(url, governor, "quorum(uint256)", snapshot)[0]
        eta = read(url, governor, "proposalEta(uint256)", proposal_id)[0]
        now = int(rpc(url, "eth_getBlockByNumber", ["latest", False])["timestamp"], 16)
        ready = bool(eta and eta <= now and state == "Queued")
        print(f"{name} | {proposal_id} | {proposal['description']} | {state} | {proposal['createdBlock']} | {snapshot} | {deadline} | {for_votes // UNIT} | {against // UNIT} | {abstain // UNIT} | {quorum // UNIT} | {eta} | {ready}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("seed", "checks", "states"))
    parser.add_argument("--rpc-url", required=True)
    parser.add_argument("--contracts", type=Path)
    parser.add_argument("--public", type=Path, default=Path("/chain"))
    parser.add_argument("--private", type=Path, default=Path("/private"))
    args = parser.parse_args()
    if args.command == "seed":
        seed(args.rpc_url, args.contracts, args.public, args.private)
    elif args.command == "checks":
        checks(args.rpc_url, args.public, args.private)
    else:
        states(args.rpc_url, args.private / "private_chain_context.json", args.public / "chain_context.json")
