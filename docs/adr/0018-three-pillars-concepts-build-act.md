---
status: accepted
---

# Three pillars: Concepts, Build, and Act

The board started with four pillars: Concepts, Transactions, Building, and Security.
The tasks people write come in three kinds. A model or an agent answers a question, the agent builds something, or the agent does something on a chain.
No task ever used Security.
So the pillars now follow those three kinds. Building is shown as Build, and Transactions takes the name Act.

## The pillars

- **Concepts holds quizzes.** A bare model or an agent answers a question, and the verifier checks the reply.
- **Build holds builds.** The agent writes contracts, pages, or apps, and the tests run what it wrote.
- **Act holds tasks where the agent acts on a chain.** It sends transactions itself, or writes a script that sends them, and the tests check what changed on the chain.

## Why Security goes

- **No task used it,** so removing it removes no task and no result.
- **Security is part of every kind of task.** A security mistake shows up as a missed quiz or as a failed check in a build or an Act task. A Security pillar would split tasks by topic while the other three split them by kind.

## Transactions becomes Act everywhere

- **The key, the folder, and the task id all change.** `tasks/transactions/<name>` moves to `tasks/act/<name>`, its `task.toml` says `pillar = "act"`, and its task id reads `act/<name>`.
- **Every Act task's hash changes,** because `task.toml` is one of the hashed files. Like any change to a task's files, that reruns every mode for the task.

## Build keeps the `building` key for now

The board and the docs say Build. The key, the folder, and the task ids still say `building`.
Whether they become `build` is still open. That rename would work like the one to `act`: it would change every Build task's hash, hide its rows, and move the folders in every open build pull request.

## Results already recorded

- **Main's 48 Transactions rows leave the board.** They come from two tasks, `send-six-decimal-token` and `supply-usdc-to-aave`. The rows stay in `results/rows.jsonl`, and their links to Harbor Hub and the release assets keep working.
- **Nothing migrates.** To show on the board, a row needs the new task id and the new task hash. Each trial's lock, Hub copy, and release asset would still record the old hash, so a rewritten row would claim files its trial never ran against.
- **The two tasks get new trials in the next paid run** after this change merges.

## Publishing

- **The Hugging Face dataset folder names change.** Each folder is published as `<pillar>--<folder>`, so `transactions--send-six-decimal-token` becomes `act--send-six-decimal-token`. A release replaces the dataset's `tasks/` folder in one commit, so the old names leave its main branch. Earlier `gh-<commit>` tags still have them.
- **A task's registry name doesn't change.** It is `buidlguidl/<name>` and has no pillar.
- **Harbor Hub doesn't change.** It keys uploads by Harbor's job and trial ids, which have no pillar.

## Considered options

- **Rename only the label.** Keep `transactions` as the key and show "Act" on the board. No hash changes and no row leaves the board, but the folders, task ids, and docs would use a different word from the board for as long as the pillar exists.
- **Rewrite the old rows.** It is cheap, two id and hash pairs across 48 rows, but each row would claim a task hash its trial never ran against.
- **Keep Security for later tasks.** An empty pillar is one more name in the docs and on the board with nothing in it, and security already fits inside the other three.
