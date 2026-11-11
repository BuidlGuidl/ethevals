---
status: accepted
---

# Ask again when a trial gets no answer

A model sometimes gives nothing to check: it refuses, or its final reply to a Concepts task is empty.
A bare model's empty reply was recorded as a fail with "The answer is empty.", so a provider hiccup counted against the model.
Fourteen saved rows failed that way.
An agent's refusal was an error that never got a retry and stayed out of the score, so a model that refused a task lost nothing on the board.

## The decision

- **No answer is a refusal, or an empty final reply to a Concepts task.** A reply that explains why the model won't help is a reply, and the checks decide it.
- **The trial is asked again right away, once.** The second ask happens inside the same CI job, with no one starting it. It adds no scored trial.
- **No answer twice is a fail.** It counts in the score like any other fail.
- **The row says what happened.** It records that the trial got no answer and the stop reason the provider gave, so the board can label the trial.
- **One rule covers agents and bare models.**
- **Other errors keep their rule.** A crash or a plan limit still gets one retry on the next CI run.
- **The second ask reserves no extra budget.** A try that ends in no answer has spent little, and the budget gate stays as it was.
- **The fourteen saved rows become errors,** so the next CI run gives each one a fresh trial.

## Considered options

- **Keep counting an empty reply as a fail the first time.** One provider hiccup then costs a model a trial out of two.
- **Record no answer as an error and leave it out of the score.** A model that refuses a question would keep a clean score, and the board would hide the refusal.
- **Retry no answer on the next CI run, like other errors.** The board would show a hole until someone pushed again, for something a second ask settles in seconds.

## Known gaps

- **An agent can spend up to its cost limit and then give no answer.** The second ask can spend the limit again, and the budget gate does not reserve for it.
