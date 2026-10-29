---
status: accepted
---

# Rejudge saved voting source with explicit provenance

Two saved Claude voting submissions finished normally and passed compilation.
Their source judge failed on missing deployment evidence and a malformed structured reason.
Repeating their agents spends money without repairing either cause.

## Decision

The voting completion boundary requests structured reason objects through the provider's JSON schema.
The provider returns one array of named workflows, so the schema defines the shared reason shape once.
The verifier requires every expected name exactly once before converting the array into RewardKit's named entries.
This avoids the provider grammar-size limit reached by eight separately nested reason schemas.
It checks every required field before encoding reasons for RewardKit's string parser.
Missing fields, invalid citations, and unknown decisions remain verifier errors.
There is no reply repair, default reason, or automatic paid retry.

Future voting deployments record the governor's actual creation receipt in public chain context.
The source bundle includes only its public address, block, and transaction facts.
Historical recovery cannot substitute a fresh chain or submitted claims for missing deployment evidence.
The two saved bundles contain no trusted governor creation receipt.
Their exact deployment block remains unproved.
Their locked public deployment protocol proves a lower bound of block 5.
The starter enables automining before setup deploys Token and Protocol in successive completed commands.
The deployment script then creates VoteToken, TimelockController, and TokenGovernor with `--slow`.
Foundry 1.5.1 sends each transaction after the previous transaction succeeds.
Those five creations therefore occupy successive or later blocks.
Recovery adds this public lower bound with the original source revision, file digests, and public deployment address.
The proof states its assumptions and does not claim an exact historical receipt.
It contains no private proposal facts or prior verdicts.

Two explicit CLI commands plan and execute a voting source rejudge.
Planning requires a checked saved job, a completed agent, and a failed source verification.
The plan binds the original task identity, saved evidence, compile record, and verifier files by content digest.
Execution checks these digests again and claims the plan once before any provider call.
It runs trusted RewardKit criteria on the saved sources and added public proof without Harbor or sidecars.
It executes no submitted code.
Each plan permits one judge call and keeps unknown costs reserved.
Another execution requires a new reviewed plan and reserve.

Recovery records retain the source task hash and agent measurements.
They record a separate verifier digest, recovery identifier, source job digest, and added judge cost.
They do not claim that an agent ran against the corrected task.
The original job, replies, results, and rows remain unchanged.
Recovery creates a new checked job with the original records beside its new verifier output.
The added recovery provenance survives row recovery and the existing results PR flow.
The existing row identity and retry number stay unchanged.
The later completion time selects the recovered row when results fold.
Original records remain available in the recovery archive and original public artifacts.

The existing publication check covers the new job while the judge credential exists.
Changed inputs or a failed secret check prevent publication.
No command uploads results or opens a PR.

## Rollout

Changing voting task files changes its Harbor task hash.
A normal merge therefore admits sixteen internet trials under the new hash.
Eight eligible agent configurations each run two trials.
The other eight configured agents support vanilla mode and cannot run this Build task.
Rejudged rows retain the old hash and do not fill the new board catalog's cells.
This change does not alter CI admission or make old submissions current-task results.
The current fresh-task plan reserves $592, including retries and judge costs.
Before merge, the parent must review that plan and the remaining $592 authorization.
Use the existing zero-budget setting to prevent paid admission until that review finishes.
For a recovery-only release, keep the published catalog at the original task revision.
Publish reviewed recovery rows through the existing results PR flow after secret checks.
Updating the catalog to the corrected task remains a separately budgeted rollout within the same authorization.

## Existing recovery

Harbor 0.24.0 provides artifact-only regrade for separate verifiers.
Its `check_task_regradable` rejects voting's shared verifier.
The shared verifier runs builds and needs the original chain during evidence collection.
Changing the task to separate mode exceeds this recovery's scope.
The new path reuses RewardKit's judge, guard, aggregation, and reward writer directly.
Free replay checks prove the boundary and provenance, not live judge accuracy.
