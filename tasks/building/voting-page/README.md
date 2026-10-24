# Governance voting page

The user asks for a Governance page for TOKEN holders.
This draft task seeds a local chain and checks only frontend compilation.
It exports the project for hand trials before browser checks are added.

## The instruction

```text
Tally is gone, so our holders need our own voting page. The governor, its timelock and the vote token are deployed on the chain in chain_context.json, and TOKEN is the token holders own. Add a Governance page to this project where a connected holder can wrap TOKEN into votes, delegate them and see how many votes they have, see every proposal with its status, the votes for and against, whether it has reached quorum and when voting ends, and vote on the open ones. Holders only. The team queues and executes from our safe.
```

## What it touches

The environment copies the savings page's create-wagmi project and committed lockfile.
The agent gets contract sources and ABI arrays under `/workspace/contracts/`.
The chain context names TOKEN, the vote token, governor, and timelock on chain 31337.
The chain needs no fork or RPC key.

Setup deploys PR #37's unchanged Token, Protocol, VoteToken, TokenGovernor, and Deploy script with OpenZeppelin 5.7.0.
The timelock owns Protocol and holds 10 ETH.
Four private holders wrap and delegate 12 million of the 100 million TOKEN.
The deployer keeps 88 million unwrapped TOKEN.
Default Anvil keys hold no tokens, votes, or timelock roles.

The agent's chain has five proposals: Executed, Defeated, Queued, Active, and Pending.
The Defeated proposal has more Against votes than For votes.
The Active proposal has 2 million For and 0.5 million Against, with most of its voting period left.
The Queued proposal's timelock wait has not ended.
No proposal has Abstain votes or a late quorum extension.
Every proposal calls Protocol's `setFee` with a distinct value.

`seed.py checks` adds nine test proposals to a separate fork after the agent finishes.
The Mac kit exposes the same step through `kit checks`.
These proposals cover For-only quorum, late quorum extension, and queued proposals before and after their wait.
The extended proposal and its twin share a creation block.
The step stops 53 blocks before their original deadline.
Only For counts toward the governor's 4 million quorum.
The checks step needs chain controls and holder keys from private chain context.
It records IDs, descriptions, call data, and blocks in that context.
It does not deploy contracts or add test proposals to the agent's chain.

Voting uses block numbers; the timelock uses seconds.
Setup mines with 12-second intervals and leaves automining on.
It does not mine empty blocks while the agent works.
Both chains start their clocks in the past, near the wall time minus the setup blocks' elapsed time.
No check depends on wall time.

The task-local chain wrapper uses the shared chain starter and RPC filter unchanged.
It keeps 128 state snapshots in memory and retains blocks, transactions, and logs.
It releases the healthcheck only after deployment and seeding finish.
Private chain context holds proposal IDs, actions, and holder keys.
Setup derives deployer and holder keys from a fixed local value.
Contract addresses match across Docker and Mac chains, including Protocol.
The agent cannot read that context or the setup files.

## The checks

| Check | What it proves | Area |
| --- | --- | --- |
| `compile` | `pnpm build` and `pnpm exec tsc --noEmit` both pass | frontend compilation |

There are no browser checks or judges yet.
The solution does nothing, so both oracle and nop can receive reward 1.
Free-check then reports its expected nop-pass failure.

## Why it matters

The same page must distinguish wrapped balances from delegated votes and read the governor's actual quorum rules.
Late quorum changes proposal deadlines after creation.
OpenZeppelin's [governance contracts](https://docs.openzeppelin.com/contracts/5.x/api/governance) define those interfaces.
Compile checks alone give no evidence that the page handles them.

## Notes

Run these free commands from the repository root:

```sh
uv run ethevals lint --tasks tasks/building/voting-page
uv run ethevals free-check --tasks tasks/building/voting-page --output /tmp/voting-page-free-check
```

The Mac hand-trial kit lives at `/tmp/subagents/voting-page/kit/` on this machine.
It uses the same `environment/setup/seed.py` as Docker.

```sh
cd /tmp/subagents/voting-page/kit
./kit start
./kit states
./kit checks
./kit states
./kit fund WALLET_ADDRESS
./kit prepare EXPORTED_PROJECT_TAR NEW_DIRECTORY
./kit run NEW_DIRECTORY
./kit txlog --since BLOCK
./kit stop
```
