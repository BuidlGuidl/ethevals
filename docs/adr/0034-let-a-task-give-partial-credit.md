---
status: accepted
---

# Let a task give partial credit

A trial passed only when its reward was 1, and a task's score was its passed trials over its scored trials.
That fits a task where one failed check means the work can't be used: a contract with one hole, a page that asks for the wrong approval.

It does not fit the audit tasks in [issue #109](https://github.com/BuidlGuidl/ethevals/issues/109).
Each one checks an agent's report against one to eight findings that professional auditors made on the same code.
In three trials of one of them, three agents found 3, 3 and 2 of its 6 findings.
Under the old rule all three score 0, and so would nearly every trial of every audit task.
The 16 tasks would add 16 zeros to every model's Build score and tell no two models apart.

## The decision

- **A trial's reward is a number from 0 to 1.**
- **A task's score is the average of its scored trials' rewards.** A pass counts 1 and a fail counts 0, so for every task on the board today the average equals the old pass rate and no score changes.
- **All-pass stays the default.** A task's reward is 1 only when every check passes, unless the task gives partial credit.
- **A task can give partial credit.** Each of its criteria then earns an equal part of the reward: a trial that meets 3 of 6 gets 0.5. This is for a task whose criteria are separate things to find, where finding some of them is still useful work.
- **Each criterion counts once.** There are no severity weights. Audit firms rate on different scales, so a weight would compare the firms and not the agents.
- **Code checks on such a task are shown and carry no weight.** The audit tasks have one, that a report exists. With no report the judge answers no to every criterion, so the reward is 0 either way.
- **A trial still passes only when its reward is 1.** A row's status keeps its three values, and "failed" covers every reward below 1. The board reads the reward for the score.
- **Pillar and overall scores keep their formulas.** A pillar score averages its task scores, and overall averages the pillars.
- **Cost per pass divides by total reward.** For all-pass tasks that is the same number as before.

## Worked cases

One trial of an audit task with 6 findings:

| What the agent does | Reward |
| --- | --- |
| Finds all 6 | 1, and the trial passes |
| Finds 3 | 0.5 |
| Finds 2 | 0.33 |
| Writes a report where nothing matches | 0 |
| Writes no report | 0 |
| Refuses twice | 0, as on any task |
| Crashes or reaches a plan limit | an error, which stays out of the score as on any task |

Two trials with rewards 0.5 and 0.33 give the task a score of 42%.
On an all-pass task, a pass and a fail give 50%, shown as 1/2.
A task with one finding gives 0 or 1 on every trial, like an all-pass task.

## How a task declares it

The judge file and the reward file both use RewardKit's weighted mean, and the reward file gives every code check file a weight of 0:

```toml
# tests/judge.toml
[scoring]
aggregation = "weighted-mean"
```

```toml
# tests/reward.toml
[scoring.report]
aggregation = "all-pass"

[[reward]]
name = "reward"
aggregation = "weighted-mean"
weights = { judge = 1, report = 0 }
```

Lint accepts this shape and no other mix: one judge file with `guard = "flag"`, every criterion a required yes-or-no question with a weight of 1, and no weight on anything but the judge.
The task catalog says whether each task is all-pass or gives partial credit, so the board does not guess from the numbers.

## What the board shows

- **A partial-credit task's cell shows its score as a percent.** An all-pass task keeps its count of passed trials, such as 1/2.
- **A partial-credit trial shows its reward as a percent,** such as 50%, in place of PASS or FAIL. Its checks still list each criterion with the judge's reason.
- **The task tooltip says a pass is 1, a fail is 0 and partial credit is in between.**

## Consequences

- Nothing is rerun or regraded. Every saved row already holds its trial's reward, and the row format does not change.
- A plain Harbor run of a published task gives the same reward the board shows, because the task's own tests compute it.
- The free check is unchanged. It leaves the judge out, so the oracle run's report gives a reward of 1 and the nop run gives 0.
- A partial-credit score is not a pass rate. Build will mix the two once the audit tasks land.
- Every task still weighs the same in its pillar. The 16 audit tasks will be 16 of Build's 25, so a model's Build score will mostly follow how it audits.
- A model's Build score can rise or fall when the audit tasks land. It rises when the model's average on audits is above its average on the other Build tasks.
- A judge's wrong answer moves a partial-credit trial by one criterion. On an all-pass task it can flip the whole trial.
