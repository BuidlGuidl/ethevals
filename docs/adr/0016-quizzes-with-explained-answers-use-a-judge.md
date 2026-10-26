---
status: accepted
---

# Quizzes with explained answers use a judge

A quiz's check has been a pattern rule on the final reply.
That works when the answer has one form, like a number or an address.
It breaks when the model explains the answer in its own words.
On `wallet-atomic-ready`, only 2 of 7 right replies, worded seven ways, passed the rule, and a reply with the meanings swapped passed.
On status 600 and Permit2, the rules failed 3 of 10 right replies, and each passed a reply that hedged between two answers.

## The split

- **A fixed-form answer keeps its pattern rule.** Yes or no, a number, an address, an exact string, or a name.
- **An explained answer gets a RewardKit judge,** with one binary criterion named like the rule it replaces.
- **The first three are `wallet-atomic-ready`, `wallet-batch-status-600` and `swaps-permit2-zero-expiration`.** The other quizzes keep their rules.

## What the judge sees

- **The question, the right answer, and the final reply,** inside RewardKit's own judge framing. The criterion holds the question word for word and the right answer with its source. `test.sh` writes the final reply to `/logs/verifier/final-reply.txt`, and the judge reads only that file.
- **It doesn't read the trajectory.** With a trajectory, RewardKit asks the judge to weigh the process as well as the outcome, and a quiz grades only the answer. The trajectory also holds the model's reasoning, and in internet and skills modes every tool call and search result.
- **Lint accepts this shape for a judge,** next to the trajectory judge that build tasks use.

## What counts as right

- **Any wording, order or format of the right answer passes,** including a reply that repeats the question or adds correct detail.
- **Swapped meanings fail.**
- **A reply that hedges between two answers, or contradicts itself, fails.**
- **A reply that offers a wrong answer fails, even next to the right one.** Naming a wrong answer only to set it apart is fine.

## The judge

- **Claude Opus 5.5 at high effort,** `anthropic/claude-opus-5-5`, the board's judge in `runner/ethevals/job.yaml`.
- **Changing the judge model is a new decision.** The judge TOMLs and `job.yaml` change together, because the board overrides the TOML and a plain Harbor run doesn't. Every quiz's hand cases then run again on the new model.
- **Hand cases sit next to each test,** in `tests/hand-cases.json`. Each case is a reply and its correct mark, and the oracle's reply is one of them, since the free check never runs the judge. A quiz switches to a judge only when every case gets its mark. All 44 cases for the first three do, and one judge call costs about $0.008.
- **Hand cases are written against the right answer, not copied into the prompt.** They're part of the task, so they're published, and adding one changes the task hash and reruns that quiz's trials.

## Free check

The free check drops judge files, so each judged quiz keeps one programmatic check, `answered`: the final reply isn't empty.
The oracle passes it and the nop agent fails it, which proves the wiring without a key.

## Known gaps

- **Opus 5.5 also takes the quiz,** so the judge grades its own model's replies. The hand cases are the guard. Every open-model fail is still read by hand before a quiz ships, and in a quiz's first judged round, so are Opus's passes.
- **A judged quiz costs a judge call per trial,** and a plain Harbor run needs the user's own judge key.
- **A reply no hand case resembles can still be misjudged.** A wrong mark found later becomes a new hand case.

## Considered options

- **Keep loosening the rules.** Each loosening followed one reply that failed, and the atomic rule still fails 5 of 7 right replies.
- **Judge every quiz.** A fixed-form answer gains nothing from a judge and pays for a call every trial.
- **Let the judge read the trajectory, as build tasks do.** It would see the model's reasoning, which the question doesn't grade.
