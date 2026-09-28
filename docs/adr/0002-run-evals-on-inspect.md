---
status: proposed
---

# Run evals on Inspect

The runner is built on UK AISI's [Inspect](https://inspect.aisi.org.uk/). Inspect already handles containers, epochs, retries, logs, token counts, and model providers. `inspect_swe` drives Claude Code, Codex CLI, and OpenCode inside a container. Writing all of that ourselves would take the sprint before the first eval ran.

We use Inspect's words where they fit: epoch, target, scorer, grader, and `/workspace`. The grader is the model that answers a rubric, and runs under Inspect's `grader` model role. Our eval folder stays our own format, so authors never write Inspect code (see [ADR 0003](0003-eval-folder-is-a-declaration.md)).

The status stays `proposed` until one test passes:

- One quiz runs in the vanilla mode, and the ERC-20 build runs with Claude Code on Opus 5.5. Both produce results rows.
- Forge test output becomes named checks.
- A killed eval run resumes without repeating finished epochs.

If the test fails on containers or services, we write our own runner in TypeScript instead. If only the harness bridge fails, we write our own agent solver and keep the rest of Inspect.

The draft spec in PR #4 (branch `spec/eval-format`) was written before this decision and is retired. It is not a source for this system.

## Considered options

- Our own runner: full control, but containers, retries, logs, cost tracking, and a log viewer would all be ours to build and keep working.
