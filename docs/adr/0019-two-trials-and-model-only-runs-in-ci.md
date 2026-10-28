---
status: accepted
---

# Two trials, and Model only runs in CI

The board needs every cell filled before the first showing: every agent on every task, and every bare model on every quiz.
CI planned only the internet mode at three trials, so bare models never got a quiz trial, and the third trials took runner time that the first two still needed.

## The decision

- **`n_attempts` is 2.** Every task, agent, and mode gets two scored trials.
- **CI plans the internet and vanilla modes.** The skills mode stays out of CI.
- **Fable 5.1 and GPT-6 Astra join the vanilla agents,** so the Model only table lists the same models as the agent tables.
- **A vanilla trial's cost limit is $2.** It makes one API call with no tools, and the $20 agent limit made the reserve for 216 quiz trials larger than the CI budget.
- **The board shows trials up to `n_attempts`.** The catalog carries `n_attempts`, and the site drops rows with a higher trial number. Third trials already recorded stay in `results/rows.jsonl`.
- **The budget gate and the retry rule are unchanged.**

## Consequences

- The Model only view goes live. It shows the Concepts quizzes, the only tasks that declare the vanilla mode.
- Raising `n_attempts` again brings the hidden third trials back onto the board and plans the missing ones.
