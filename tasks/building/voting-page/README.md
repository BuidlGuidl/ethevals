# Governance voting page

Tally has shut down, and a protocol's token holders need their own page to wrap, delegate and vote.
The agent adds a Governance page to a create-wagmi project, for a deployed OpenZeppelin governor.
Three of the governor's rules differ from what most pages assume:

- Only For votes count toward quorum.
- A late quorum moves the end of voting.
- Votes count at each proposal's snapshot.

The checks drive the built page in a browser. They compare what it shows, and what it asks the wallet to sign, with the governor.

Every number on a voting page has a source on chain, and a page can guess each one from events and defaults instead.
Live pages make those guesses today.
This task checks whether the page reads them.

## The instruction

> Tally is gone, so our holders need our own voting page. The governor, its timelock and the vote token are deployed on the chain in chain_context.json, and TOKEN is the token holders own. Add a Governance page to this project where a connected holder can wrap TOKEN into votes, delegate them and see how many votes they have, see every proposal with its status, the votes for and against, whether it has reached quorum and when voting ends, and vote on the open ones. Holders only. The team queues and executes from our safe.

## What it touches

The request names what holders must see.
It doesn't say where each value comes from, and four of them go wrong when a page computes them itself.

- **Status.** Pending, Active, Defeated, Succeeded, Queued and Executed come from the governor's `state()`. A page that works status out from the creation event and the tallies is wrong at the deadline, on a tie, and whenever the end moves.

- **When voting ends.** The first time For votes reach quorum late, this governor extends voting by 7,200 blocks and emits `ProposalExtended`. The end block in `ProposalCreated` is then stale, and only `proposalDeadline()` is right.

- **Quorum.** `COUNTING_MODE()` here is `support=bravo&quorum=for`, so Abstain votes don't count toward the 4 million quorum. OpenZeppelin's default counts For and Abstain together. So does any page that hard-codes that default. With For 3M and Abstain 2M, it shows "reached" for a proposal the governor will defeat:

  | Counting | Counted toward the 4M quorum | Quorum |
  | --- | --- | --- |
  | For and Abstain, OpenZeppelin's default | 5M | reached |
  | For only, this governor | 3M | not reached, so the proposal is Defeated |

- **Whose votes count.** Wrapping TOKEN gives vote tokens but no votes, because the wrapper doesn't delegate for the holder. A vote on a proposal weighs what the holder had delegated at its snapshot, not what they hold now. A holder who delegates late goes through this:

  1. A proposal's snapshot passes while the holder has no votes delegated.
  2. The holder wraps and delegates. Their wallet now shows 1,000 votes.
  3. The holder votes For on that proposal. The transaction succeeds, and the vote weighs 0.

  A page that trusts the receipt tells them their vote counted.

## The checks

The agent starts with the create-wagmi project and the contracts' sources and ABIs under `/workspace/contracts/`. It also gets `chain_context.json`, which names TOKEN, the vote token, the governor and the timelock.
Its chain has five ordinary proposals: Executed, Defeated, Queued, Active and Pending.

After the agent finishes, the verifier builds the page and starts its own fork of that chain. On the fork it adds nine test proposals the agent never saw. They include:

- one that reaches quorum only if Abstain counts
- a late-quorum proposal and a twin created in the same block
- queued proposals before and after their wait

It opens the page with an injected wallet, acting as holders it finds in public `DelegateChanged` logs. It follows the page's own tabs, links and vote dialogs, and compares what it reads with the governor.

| Check | What it proves | Area |
| --- | --- | --- |
| `compile` | `pnpm build` and `pnpm exec tsc --noEmit` both pass | frontend compilation |
| `lists_every_proposal` | The page lists all five ordinary and nine test proposals | proposal discovery |
| `status_and_tallies_match` | Every status and For/Against tally matches the governor, before and after the twins' original end | governor reads |
| `quorum_counts_for_only` | For plus Abstain over 4 million doesn't show quorum reached; passed and extended proposals do | counting rules |
| `end_moves_with_late_quorum` | The extended proposal shows a later end than its twin, stays open after the twin closes, and takes a vote with weight | voting end |
| `wrap_then_delegate` | A holder wraps 1,000 TOKEN, sees 0 votes until delegating and 1,000 after | voting power |
| `votes_at_snapshot` | A holder who delegated after a proposal's snapshot sees 0 votes on it or can't vote on it, then casts their full 1,000 For on a new proposal | snapshot votes |

A check fails a page only for what the page showed or asked the wallet to sign.
When the verifier can't read a value or finish a flow, it records "could not drive" for that check and goes on. Then:

- Every check passes: the reward is 1.
- Any check fails: the reward is 0.
- Nothing fails, but some check could not be driven: the trial is an error for a human to look at.

## Why it matters

DAOs now build these pages themselves.
[Tally announced it was shutting down](https://newsletter.tally.xyz/p/tally-is-shutting-down) in March 2026, and Arbitrum [built its own governance page](https://forum.arbitrum.foundation/t/governance-ui-update/30837) with Offchain Labs.

The live pages that remain make the guesses this task checks:
- **Agora**
  - It [works status out](https://github.com/voteagora/agora-next/blob/e1cda9ce38a741aaafaa62ef6fc906eced477449/src/lib/proposals/status/deriveStatus.ts#L30-L60) from indexed events and its own vote maths, rather than `state()`.
  - It [counts quorum](https://github.com/voteagora/agora-next/blob/e1cda9ce38a741aaafaa62ef6fc906eced477449/src/lib/proposalUtils.ts#L1110-L1142) through a hard-coded switch per DAO, For plus Abstain by default.
  - It lets a holder with [zero voting power cast a vote](https://github.com/voteagora/agora-next/blob/e1cda9ce38a741aaafaa62ef6fc906eced477449/src/lib/voteUtils.ts#L273-L276).
- **nouns.wtf** shows a [quorum threshold of 0](https://github.com/nounsDAO/nouns-monorepo/blob/2213eea1c15f331f786784c2621d53bdecf907e2/packages/nouns-webapp/src/pages/Vote/index.tsx#L727) for proposals whose quorum read never runs.
- **Tally Zero**, offered to DAOs as Tally's open replacement, [never scans the last partial block window](https://github.com/withtally/tally-zero/blob/4f9ec8d076e0bdd58b08c8910655c93bfff06e95/hooks/use-search-proposals.tsx#L38-L42), so the newest proposals, the open ones, are missing.

OpenZeppelin's [governance API](https://docs.openzeppelin.com/contracts/5.x/api/governance) defines `state`, `proposalDeadline`, `COUNTING_MODE`, `quorum` and votes at a timepoint.
A page that reads them shows holders what the governor will do. A page that guesses can tell a holder their vote counted when it weighed nothing.

## Notes

- "Holders only" can mean that only holders vote, or that only holders see the page. Every journey connects a wallet that holds TOKEN or vote tokens, so either reading passes.
- No check scores approval amounts, Abstain display, network switching, or the team's queue and execute controls. The team acts from its safe.
- The checks accept these variations:
  - wrapping and delegating in one action
  - an end shown as a block, a date or a countdown, compared by order when both ends use the same unit
  - for a holder with no votes at the snapshot, either a 0 shown or no usable vote control

  A For vote must send support 1, and the governor must record it For with the holder's full weight.
- **The chain.**
  - Setup deploys the `token-governor` task's contracts unchanged, with OpenZeppelin 5.7.0. The timelock owns Protocol and holds 10 ETH.
  - Four holders wrap and delegate 12 million of the 100 million TOKEN. The deployer keeps the rest unwrapped. Anvil's default accounts hold nothing.
  - Voting runs in blocks and the timelock in seconds. No check depends on wall time.
- Setup makes its keys at random inside the chain container. The agent can't read them or the setup files, and the verifier needs no keys.
- The test proposals exist only on the verifier's fork, so the agent's chain never shows the cases the checks use.
- Pages here make many RPC reads per block, which a public RPC would throttle. No check covers that load.
- The browser and its libraries are root-only. A browser the agent downloads can't start.

Run these free commands from the repository root:

```sh
uv run ethevals lint --tasks tasks/building/voting-page
uv run ethevals free-check --tasks tasks/building/voting-page \
  --output /tmp/voting-page-free-check
```
