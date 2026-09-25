# An eval folder declares what it needs; the runner provides it

An eval is a folder of data: `eval.yaml` holds the metadata and the prompt, `starter/` holds the agent's files, `setup/` prepares the chain, and `grader/` holds all grading, a quiz's answer included. Folder names carry meaning. Only the prompt and `starter/` reach the agent. The yaml states needs, such as a fork pinned to a block, and never how to meet them. Containers, networks, and chains belong to the runner. Only `setup/` and `grader/` hold code.

With this shape, community authors add an eval without learning the runner, and tools read every eval without running it.

## Alternatives not taken

- Evals written as code, as Inspect does: every author would have to learn the runner, and no tool could read an eval without running it.
- JSON instead of yaml: no comments, and multi-line text is painful to write by hand.
- TOML instead of yaml: TOML works, and Foundry uses it. yaml wins because GitHub Actions and most tools people already touch use it. yaml reads `0x...` and `1.10` as numbers, so a schema check requires answers and addresses to be strings.
- A quiz's answer in `eval.yaml`: one file per quiz, but grading would live in two places.
- Answer-matching options in yaml, such as `match: regex`: a small language inside yaml that only grows. Anything past an exact match is a grader someone writes.

## Parked

- The prompt in its own `prompt.md`. If long prompts become a problem, the prompt moves there, or more context moves into `starter/`.
