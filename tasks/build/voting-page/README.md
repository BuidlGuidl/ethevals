# Governance voting page

Token holders need a page to wrap, delegate, and vote with the deployed governor.
The verifier compiles the submitted page and judges eight workflows from complete source and public contract evidence.

## The instruction

> Tally is gone, and our holders need our own voting page. The governor, its timelock and the vote token are already deployed (the addresses are in chain_context.json), and TOKEN is the token holders own. Could you add a Governance page to this project where a connected holder can wrap TOKEN into votes, delegate them and see how many votes they have, see every proposal with its status, the votes for and against, whether it has reached quorum and when voting ends, and vote on the open ones? It's just for holders; the team queues and executes from our safe.

## What it touches

The governor counts only For votes toward quorum.
Its late-quorum extension changes the effective deadline.
A holder's voting weight comes from each proposal's snapshot, even after later delegation changes.

Wrapping creates vote tokens without delegated votes.
The page must follow approval, deposit, delegation, receipts, and refreshed reads into the holder's displayed votes.

## The checks

| Check | What it proves | Area |
| --- | --- | --- |
| `compile` | Executed `pnpm build` and `pnpm exec tsc --noEmit` both pass | frontend compilation |
| `lists_every_proposal` | Complete successful scans reach every proposal, with honest loading and refresh errors | proposal discovery |
| `status_and_tallies_match` | Governor state and For and Against tallies reach the displayed proposal | governor reads |
| `quorum_counts_for_only` | Quorum and any progress count For votes only | counting rules |
| `end_moves_with_late_quorum` | Effective deadlines and voting gates honor extensions and snapshot eligibility | voting end |
| `wrap_then_delegate` | Approval, wrapping, delegation and refreshed current votes form a usable holder flow | voting power |
| `votes_at_snapshot` | Display and voting use the proposal snapshot through later delegation changes | snapshot votes |
| `canceled_status` | Canceled state reaches the display and prevents a vote request | closed proposals |
| `already_voted` | The connected holder cannot send a duplicate vote request | duplicate votes |
| `free_submission_changed` | Free mode only: application source differs from the untouched starter | free check |

RewardKit 0.2.3 owns judgment, guard, named checks, aggregation, usage records, and both reward files.
One Opus 5.5 high-effort judge owns the eight workflows.
Each decision includes a causal trace and file/line citations.
The provider response schema requires a structured reason object with every field, including `limitations`.
The verifier checks the object before encoding it for RewardKit's string parser.
It follows reachable controls through reads, UI state, handlers, transaction targets and arguments, receipts, and refresh.
Any control wording and component names can pass.
Source judgment establishes implementation behavior, not successful browser or transaction execution.

The bundle includes full application sources and helpers outside `src`.
It includes package and configuration inputs, public deployment context, and full supporting contract sources and interfaces.
A static TypeScript parser discovers imports and ordinary local aliases without executing configuration.
Computed imports, unsupported aliases or local packages, missing imports, unsafe paths, missing public context, and oversized input raise verifier errors.
HTML scripts also participate in import checks.
Submitted chain context retains its exact bytes; trusted deployment facts use `public-deployment/chain_context.json`.
No file is silently truncated.
The manifest records file hashes, line ranges, inclusion reasons, omissions, and unresolved boundaries.
Submitted files remain untrusted evidence inside RewardKit's guard.

A concrete compilation or workflow failure gives reward zero.
Every check must pass for reward one.
An unknown decision, incomplete response, bad citation, provider error, or timeout gives a verifier error.
The task permits one provider request with automatic retries disabled.
The output limit is 24,576 tokens.
Build commands receive no provider keys.
`reward-details.json` retains structured reasons and normal usage.
Invalid replies retain available usage and error records, with no reward file.
Each invocation clears earlier reward files before checks begin.
Production judges available source even after compilation fails, so the board retains its required judge record.
`source-decisions.json`, the request, response, bundle, and manifest support inspection.

## Why it matters

Governance pages must show what the governor will count and permit.
A successful zero-weight receipt cannot prove that the page used the correct snapshot weight.
A polling interval cannot bound data age after failed refreshes.

OpenZeppelin's [governance API](https://docs.openzeppelin.com/contracts/5.x/api/governance) defines the reads behind these workflows.
[ADR 0021](../../../docs/adr/0021-judge-voting-page-workflows-from-source.md) records the score owners and error policy.

## Notes

The instruction, governor behavior, and solution stay unchanged.
The verifier no longer runs the task's browser driver or creates hidden test proposals.
No browser selector or `couldNotDrive` prerequisite contributes to production scoring.
The public chain context supplies deployment addresses and the governor's actual creation receipt.
The receipt records the creation block and its block and transaction hashes.
Private chain context never enters judge input.
The environment keeps a root-only copy of public contract sources for the verifier.

The repository free check removes the judge file.
It executes compilation and compares application source with the starter.
The solution passes this comparison and untouched work fails it.
A changed comment can pass that comparison; it proves no workflow semantics.
Replay tests exercise the parser, guard, named results, aggregation, and usage path without a model call.
Paid judge validation remains separate.
Saved submissions can use the [reviewed recovery path](../../../runner/README.md#ci-and-publication).
Recovery keeps their original task hash and adds separate verifier provenance.
Their saved bundles lack trusted creation receipts, so their exact historical deployment blocks remain unproved.
Recovery can add the lower bound from their locked public deployment protocol, with source digests and explicit assumptions.

Run from the repository root with all provider keys unset:

```sh
uv run ethevals lint --tasks tasks/build/voting-page
uv run pytest -q tasks/build/voting-page/verification/test_source.py
uv run ethevals free-check --tasks tasks/build/voting-page --output /tmp/voting-page-free-check
```
