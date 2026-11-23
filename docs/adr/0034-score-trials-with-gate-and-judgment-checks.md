---
status: accepted
---

# Score a trial with gate checks and judgment checks

A trial passes only when every check passes, and the board shows how many trials passed.
That rule hides what the trials show.

- **Two Build tasks read 0 for every agent.** `token-governor` and `aave-savings-page` each have one check that no agent passes.
- **An audit trial that finds 7 of 8 known findings fails,** the same as one that finds none.
- **Good work and no work look the same.** A trial that misses one check of four counts the same as a trial that hands in nothing.

Other benchmarks can stay strict because their tests check only what the instruction says.
Ours also check what an experienced Ethereum developer does without being told, so one missed check is not the same as a failed request.

## The decision

Every check in a Build or Act task is one of two kinds.

- **A gate check** tests something the instruction asks for.
- **A judgment check** tests something an experienced Ethereum developer gets right without being told.

```text
trial score
  a gate check fails     -> 0%
  every gate check passes -> checks passed ÷ all gate and judgment checks
```

One `token-governor` trial:

| Check | Kind | Result |
| --- | --- | --- |
| quorum counts the whole supply | gate | pass |
| the delay guards the money | gate | pass |
| snapshot can run it | gate | pass |
| late votes extend the vote | judgment | fail |

All three gate checks pass, so the trial score is 3 of 4, 75%.
Had the quorum check failed, the trial score would be 0%.

- **Entry checks only show that something was handed in.** They are `compile`, `answered`, `no_answer`, and `report_written`. A failed entry check makes the trial score 0%. A passed one earns nothing and stays out of the division.
- **A task with only gate checks stays all or nothing.** So does a Concepts task, whose one check is right or wrong.
- **On an audit task, each known finding is a judgment check,** and `report_written` is its entry check. The instruction does ask for findings, so this is an exception to the gate rule. As gate checks they would put every trial that misses one finding at 0%.
- **A task score is the mean of its trial scores.** Errors stay out. Pillar scores and Overall average as before.
- **Saved trials are scored from their saved checks.** This decision reruns no trial, regrades none, and asks no judge again.

## Where the tags live

- **Each task tags its own checks** in `task.toml`, under `[metadata.checks]`, as `check name = "gate"` or `check name = "judgment"`.
- **Every Build and Act check has a tag.** An untagged check has no default. Concepts tasks have no table.
- **The tags stay out of the instruction, environment, and checks hashes.** A tag never changes whether a check passed. It only changes how the saved results add up, so no saved result goes stale. [ADR 0030](0030-regrade-from-saved-check-output.md) kept its statement inside `tests/` because that statement is about what the checks decide. A tag is not.
- **Only this one table is exempt.** Any other new key in `task.toml` changes the environment hash and reruns the task, so a later scoring setting needs its own decision. Lint rejects a `[metadata]` key it does not know.
- **Lint checks the tags.** It reads Forge test names and judge criteria from the task's files. It fails on a missing tag, a tag on an entry check, and a table on a Concepts task. Where those files name every check, it also fails on a tag for a check the task does not have.
- **The free check covers the names lint cannot read.** A custom verifier's check names only appear when it runs. The free check fails when a run reports an untagged check, and when a tag matches no reported check and no criterion.
- **A trial that does nothing scores 0%.** The free check's nop run must fail a gate check or an entry check. Failing only a judgment check is not enough, because the trial would keep credit for the checks it passed.
- **Entry checks are a fixed list of names in shared code.** The tools that write them are not changed.

## Where the score is worked out

- **The site works out the trial score** from each row's saved checks and the tags in the task catalog. Result rows keep their shape and their schema version.
- **A row can carry a check name the tags do not know,** because the board keeps a row whose checks hash is behind. That check is left out of the division and is never a failed gate. A tagged check that a row lacks is ignored. When nothing is left to count, the trial is 100% or 0% from its reward.
- **Harbor's `reward` stays `all-pass`.** The board and a plain Harbor run can now disagree: Harbor says pass or fail, and the board says a percentage. This replaces the line in [ADR 0011](0011-verifiers-use-rewardkit-and-criteria-run-in-the-task.md) that they cannot disagree, and the line in [ADR 0010](0010-run-tasks-on-harbor.md) that the board shows a count.

## Considered options

- **Passed checks ÷ all checks, with no gate.** A trial that fails what the instruction asked keeps most of its credit, and the six strongest agents end up within about 4 percentage points.
- **Weights per kind of check.** The weights are numbers picked by hand.
- **A gate check is one that is unsafe to miss.** Whether the instruction asks for something can be read off the instruction. Whether a miss is unsafe is a fresh call for every check.
- **A check that mixes an asked part with an unasked detail is a judgment check.** A trial that fails the asked part would then keep credit. Such a check is a gate check.
- **Tag only gate checks and treat the rest as judgment checks.** A forgotten tag would turn a 0% into credit without any warning.
- **Tags in a site file.** A new task would need a second edit far from the task, and a renamed check would lose its tag silently.
- **Tags inside `tests/`.** The checks hash changes, and a regrade asks the judge again on every task that has one, even with `tests/regrade-from.json`.
- **Each tool marks its own entry checks.** `compile` is written by a file in the shared chain image. Editing it changes the image tag and reruns every Build and Act task. `report_written` sits in each audit task's tests, and editing it reruns the audits.
- **The runner writes the score into each row.** A new row field invites a schema version change, and the planner then sees no saved rows and plans the whole board again.

## Known gaps

- Harbor Hub shows pass or fail for a trial the board scores as a percentage.
- Editing a tag changes old scores with no new result row. Only the task's history shows it.
- Check names are written twice, in the tests and in `task.toml`.
- The free check skips a task whose host variables are unset. For those tasks a custom verifier's check names, and a tag for a check that no longer exists, are only checked where the variables are set.
