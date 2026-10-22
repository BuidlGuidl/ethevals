# Add a task

For Harbor mechanics, read the [create-task skill](../.agents/skills/create-task/SKILL.md).
Before writing a verifier, read the [RewardKit skill](../.agents/skills/rewardkit/SKILL.md).
The rules below govern the board.

Start with the closest real task below.
Its files and shared images are the conventions; free checks keep these examples working.

| Work | Closest example |
| --- | --- |
| A question with a fixed answer | [Agent registries](../tasks/concepts/agent-registries/) checks the final reply against a target. |
| Writing or repairing code | [Revenue payouts](../tasks/building/revenue-payouts/) checks submitted Solidity with Forge, without a chain sidecar. |
| Acting on a fresh chain | [Send a six-decimal token](../tasks/transactions/send-six-decimal-token/) includes setup, private chain context, and criteria. |
| Acting on a fork | [Supply USDC to Aave](../tasks/transactions/supply-usdc-to-aave/) pins chain state and keeps the upstream RPC secret inside its sidecar. |

For Security work, choose the example with the same environment and verifier needs.
The pillar describes the work, not its tools.

## Board rules

Write the instruction as a real user's request.
Keep tests, targets, criteria, and solutions out of the agent's starting files.
The board measures ordinary work; knowledge of the checks can change how an agent acts.

Keep task-specific facts and setup inside the task folder.
Declare only the sidecars the task needs.
An outside Harbor run must use the same task as the board, without changes to shared runner code.

Use vanilla for questions a bare model can answer in one reply.
Use internet and skills for work that needs an agent's tools or environment.
Keep agent selection, `n_attempts`, and retry limits in the board's job config.

Check the requested outcome, and give each failed check a reason that explains what went wrong.
Every check must pass for a trial to pass.
Split distinct requirements into named checks so a failure remains useful to readers.
Use criteria for requirements that need a judge's judgment.
Review those questions and their declared evidence; the free check skips paid judging.

Prove the task with the [free check](harbor.md#free-checks).
The oracle run must pass every test check, and nop must fail at least one.
This catches broken solutions and checks that accept untouched work before anyone pays for trials.
If a task needs a fork secret, obtain a maintainer's passing fork check before merge.
That manual check keeps secrets away from unreviewed pull-request code.

Task files, including solutions, become public in the dataset.
Training on them is welcome; the board cannot distinguish learned answers from new work.
Keep credential values outside the task files.
If a task has judge criteria, declare its judge key through `[verifier.env]`, as the RewardKit skill shows.
