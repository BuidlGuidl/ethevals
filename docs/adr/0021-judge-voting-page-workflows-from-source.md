---
status: accepted
---

# Judge voting-page workflows from source

Browser control discovery rejected working labels and left workflows unresolved.
This decision replaces the voting-page scoring rules in ADRs 0014 and 0019.
The instruction and deployed governor behavior stay the same.

## Check owners

Executed `pnpm build` and `pnpm exec tsc --noEmit` own `compile`.
One RewardKit source judge owns these eight binary checks:

- `lists_every_proposal`
- `status_and_tallies_match`
- `quorum_counts_for_only`
- `end_moves_with_late_quorum`
- `wrap_then_delegate`
- `votes_at_snapshot`
- `canceled_status`
- `already_voted`

The judge traces controls, reads, state, writes, addresses, proposal IDs, support, reasons, receipts, and refreshes.
Every decision includes a causal trace and file/line citations.
Snapshot eligibility remains valid after later delegation changes.
Late-quorum voting cannot assume that an eligible holder retains recent delegated votes.
Listing distinguishes a successful complete scan from cached data after a failed refresh.
A polling interval proves no bound on data age.
A zero-weight receipt proves no correct snapshot display.

No browser result, captured view, wallet selector, or `couldNotDrive` result gates these checks.
The old browser and page-text scoring paths leave the task.
No retained runtime evidence contributes to workflow scores.
Source decisions describe implementation behavior, never successful execution.

## Evidence and outcomes

The bundle contains full application sources, local helpers, package/configuration files, public chain context, and relevant contract behavior.
The manifest records stable paths, hashes, complete line ranges, inclusion reasons, omitted files, and unresolved boundaries.
Submitted files and comments are untrusted evidence inside RewardKit's guard.
Verifier instructions, test expectations, private context, and earlier verdicts stay outside that evidence.
The bundle never executes submitted configuration to discover files.
Each file is limited to 400,000 bytes, with at most 3,000 file or omission records.
The complete numbered bundle is limited to 1,000,000 bytes, below RewardKit's file limit.
The completion request is limited to 970,000 bytes and output to 24,576 tokens.

Concrete build failure or a source workflow failure gives reward zero.
Production still judges available source after a build failure, so the board receives its required judge record.
Missing public context, unsupported imports, unsafe paths, oversized evidence, and incomplete evidence raise verifier errors before judgment.
An invalid or incomplete response, unknown decision, provider error, or timeout raises a verifier error.
Unknown results never pass, even when another workflow fails.
RewardKit alone writes `reward.json` and `reward-details.json`.
Its named workflow results, raw structured reasons, guard, and usage remain normal artifacts.
Response errors retain the received usage in RewardKit's error result before the verifier removes the reward.
Each invocation clears earlier reward files before any check can fail.

Submitted chain context retains its actual bytes and its application path.
The environment's original symlink can point only to the trusted public context.
Trusted deployment facts use a separate reserved path and cannot satisfy a missing application import.
HTML scripts participate in import checks, and unsupported local package references raise evidence errors.

The task uses pinned RewardKit 0.2.3 and Opus 5.5 at high effort.
A task-local completion boundary sets an output limit and disables automatic provider retries.
It validates structured reasons before RewardKit parses and aggregates the response.
It does not replace RewardKit's judge, guard, score parser, aggregation, or reward writer.
Each invocation permits one provider request.
Build commands receive no provider keys.

## Free checks and validation

The repository's free check removes judge files.
In that mode, compilation runs and `free_submission_changed` compares application source with the untouched starter.
This exact-source check distinguishes oracle from nop without claiming to test workflow semantics.
It contributes nothing to production scoring when the judge exists.
Free parser tests replay responses through real RewardKit; replay proves no live judge accuracy.
Paid validation requires separate review of exact provider inputs, output limits, prices, retries, and a reserved budget.

This changes the task hash under the existing identity rules.
It changes no runner-wide admission, aggregation, recovery, CI, or publication contract.
