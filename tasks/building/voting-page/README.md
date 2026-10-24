# Governance voting page

The user asks for a Governance page for TOKEN holders.
The checks compare displayed values, wallet requests, and vote events with the governor on a private fork.

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
These proposals cover For-only quorum, late quorum extension, and queued proposals before and after their wait.
The extended proposal and its twin share a creation block.
The step stops 53 blocks before their original deadline.
Only For counts toward the governor's 4 million quorum.
The verifier finds holders in DelegateChanged logs and impersonates them on its fork.
It keeps proposal IDs, call data, and blocks in memory.
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
Setup generates random deployer and holder keys inside the chain container.
The agent cannot read that context or the setup files.

## The checks

| Check | What it proves | Area |
| --- | --- | --- |
| `compile` | `pnpm build` and `pnpm exec tsc --noEmit` both pass | frontend compilation |
| `lists_every_proposal` | The page lists all five ordinary and nine test proposals | proposal discovery |
| `status_and_tallies_match` | Every status and For/Against tally matches the chain before and after the twins' original end | governor reads |
| `quorum_counts_for_only` | For plus Abstain cannot meet quorum; passed and extended proposals show reached | counting rules |
| `end_moves_with_late_quorum` | The extended proposal ends later, stays open after its twin closes, and accepts a positive-weight vote | voting end |
| `wrap_then_delegate` | A holder wraps 1,000 TOKEN and sees zero votes until delegation and 1,000 afterward, including a combined action | voting power |
| `votes_at_snapshot` | A new delegate sees zero weight or no usable control on an old proposal, then casts 1,000 votes on a new proposal | snapshot votes |

Reward is 1 only when every check passes.
Each check records an unknown value or unfinished flow as "could not drive" and continues.
A known failed check gives reward zero, even when another check cannot finish.
If no check fails, unresolved checks produce a trial error after RewardKit runs.
An absent Governance page fails the proposal-list check and its dependent checks.
The verifier reads vote weight from VoteCast events, rather than transaction status.
The old-proposal journey accepts a displayed zero or no usable voting control.
The new-proposal journey requires a vote with the holder's full snapshot weight.
The voting-end comparison uses order alone.
End comparisons accept blocks, dates, or countdowns when both ends use the same unit.
No check scores approval amounts, Abstain display, network switching, or team queue and execute controls.

## Why it matters

The same page must distinguish wrapped balances from delegated votes and read the governor's actual quorum rules.
Late quorum changes proposal deadlines after creation.
OpenZeppelin's [governance contracts](https://docs.openzeppelin.com/contracts/5.x/api/governance) define those interfaces.
A successful transaction can cast zero votes when the holder gained voting power after the proposal's snapshot.

## Notes

"Holders only" can mean that only holders can vote, or that only holders can view the page.
Every browser journey connects a wallet that holds TOKEN or its vote wrapper.
Pages here make many RPC reads per block, which a public RPC would throttle.
No check covers that load.
Test state lives in the verifier's fork and never changes the task chain.
The verifier needs no keys or private chain context.
Extra agent proposals remain in the list and do not prevent fixture setup.
Its browser, dependencies, and extra libraries remain root-only.

Run these free commands from the repository root:

```sh
uv run ethevals lint --tasks tasks/building/voting-page
uv run ethevals free-check --tasks tasks/building/voting-page --output /tmp/voting-page-free-check
```
