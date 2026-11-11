---
status: accepted
---

# Regrade when only the checks change

A trial's identity carried the task hash, which covers every file in the task folder.
Any change to a task reran all of its trials: a README typo, a new hand case, a fixed test.
That made a wrong check expensive to fix.
On `compiler-legacy-init-order`, Opus replied "**Answer: the zero address.**" and the answer rule failed it, because the rule wanted the reply to open with the answer.
Fixing the rule meant paying every model to answer again, and a fresh reply says nothing about whether the saved one was right.

## Three kinds of file

- **What the agent sees: the instruction and the environment.** A change here reruns the task's trials.
- **The checks: the tests and the criteria.** A change here regrades the task's trials.
- **Everything else: the README, the solution, the description.** A change here does nothing.

A setting in `task.toml` goes with the part it configures.
A file that fits no kind counts as what the agent sees, so a mistake in sorting costs a rerun and never a wrong result.

## Identity

- **A trial's identity uses the instruction hash and the environment hash** in place of the task hash.
- **A row records the checks hash** of the checks that decided it.
- **The board shows a row when its instruction and environment hashes match the task's files.** A row whose checks hash is behind keeps its last result on the board until its regrade or rerun lands, so a check fix never empties the board.
- **The task hash keeps Harbor's meaning,** the digest of the whole folder. A row still records it. Datasets, images, and the Hub keep it as the task's key.
- **Switching over keeps every trial on the board.** Each saved row gets the hashes of the files that ran and checked it.

## Regrade

A regrade decides a saved trial's checks again and never runs the agent.
The new row replaces the old one, and a changed result shows in the "Record trial results" pull request like any other.

| When this changes | The task's trials are |
| --- | --- |
| A Concepts task's tests | regraded from the saved final reply |
| Only a judge's criteria or the judge model, on any task | regraded by asking the judge again on its saved input; the other checks keep their results |
| A contract Build task's tests | regraded on the saved work |
| Tests that need a browser or a chain | rerun |
| The instruction or the environment | rerun |

- **When the saved work is gone, the trial is rerun.** A download that fails for a passing reason, such as a rate limit, is tried again on the next CI run and never becomes a rerun.
- **A regrade that fails changes nothing.** The row keeps its result, the CI job fails, and the next CI run plans the regrade again.
- **A regrade decides a row's status by the same rules as a trial.** A fail from no answer twice stays a fail.
- **A regrade that asks a judge reserves the judge's cost under the budget.** A regrade with no judge is free.
- **Every trial on a task gets the same treatment.** One fail is never regraded or rerun on its own. Fix the check, and every trial on that task is regraded.

## Consequences

- **A trial's saved work has to stay fetchable for as long as its row is on the board.** The published trajectory and verifier archive cover Concepts tasks and judges. A contract Build task also needs the files the agent left.
- **Adding a hand case regrades a Concepts task's trials.** ADR 0016 said it reran them.
- **ADR 0009's rule that a task file change reruns every mode now holds only for the instruction and the environment.**

## Known gaps

- **Shared check code that is built into an image counts as environment,** so changing it still reruns the tasks that use the image. A task's own tests are the place for a fix.
- **Browser and chain checks can't be regraded.** The chain stops with the trial. ADR 0011 rejected separate verifiers for chain tasks.

## Considered options

- **Keep one hash for the folder and rerun.** It is the simplest rule and it was the price of every check fix.
- **Edit one row by hand, or rerun one fail.** The trial we happened to read would get a second chance that the others never get.
- **Regrade everything, chain tasks too, by saving the chain.** It needs a saved chain state per trial and a verifier that can start from it.
