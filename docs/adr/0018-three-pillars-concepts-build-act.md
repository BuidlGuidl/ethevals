---
status: accepted
---

# Three pillars: Concepts, Build, and Act

The board started with four pillars: Concepts, Transactions, Building, and Security.
The tasks people write come in three kinds. A model or an agent answers a question, the agent builds something, or the agent does something on a chain.
No task ever used Security.
So the pillars now follow those three kinds. Building becomes Build, and Transactions becomes Act.

## The pillars

- **Concepts holds quizzes.** A bare model or an agent answers a question, and the verifier checks the reply.
- **Build holds builds.** The agent writes contracts, pages, or apps, and the tests run what it wrote.
- **Act holds tasks where the agent acts on a chain.** It sends transactions itself, or writes a script that sends them, and the tests check what changed on the chain.

## Why Security goes

- **No task used it,** so removing it removes no task and no result.
- **Security is part of every kind of task.** A security mistake shows up as a missed quiz or as a failed check in a build or an Act task. A Security pillar would split tasks by topic while the other three split them by kind.

## The new names go all the way down

- **The key, the folder, and the task id all change.** `tasks/building/<name>` moves to `tasks/build/<name>` and `tasks/transactions/<name>` moves to `tasks/act/<name>`. Each `task.toml` says `pillar = "build"` or `pillar = "act"`, and the task ids read `build/<name>` and `act/<name>`.
- **Every Build and Act task's hash changes,** because `task.toml` is one of the hashed files. Like any change to a task's files, that reruns every mode for the task.

## Results already recorded

- **Main's 72 Building and Transactions rows leave the board.** They come from three tasks: `revenue-payouts`, `send-six-decimal-token`, and `supply-usdc-to-aave`. The rows stay in `results/rows.jsonl`, and their links to Harbor Hub and the release assets keep working.
- **Nothing migrates.** To show on the board, a row needs the new task id and the new task hash. Each trial's lock, Hub copy, and release asset would still record the old hash, so a rewritten row would claim files its trial never ran against.
- **The three tasks get new trials in the next paid run** after this change merges.

## Publishing

- **The Hugging Face dataset folder names change.** Each folder is published as `<pillar>--<folder>`, so `building--revenue-payouts` becomes `build--revenue-payouts` and `transactions--send-six-decimal-token` becomes `act--send-six-decimal-token`. A release replaces the dataset's `tasks/` folder in one commit, so the old names leave its main branch. Earlier `gh-<commit>` tags still have them.
- **A task's registry name doesn't change.** It is `buidlguidl/<name>` and has no pillar.
- **Harbor Hub doesn't change.** It keys uploads by Harbor's job and trial ids, which have no pillar.

## Considered options

- **Rename only the labels.** Keep `building` and `transactions` as keys and show "Build" and "Act" on the board. No hash changes and no row leaves the board, but the folders, task ids, and docs would use different words from the board for as long as the pillars exist.
- **Rewrite the old rows.** It is cheap, three id and hash pairs across 72 rows, but each row would claim a task hash its trial never ran against.
- **Keep Security for later tasks.** An empty pillar is one more name in the docs and on the board with nothing in it, and security already fits inside the other three.
