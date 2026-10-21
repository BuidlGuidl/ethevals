# Add a task

Write a Harbor task folder under `tasks/PILLAR/NAME/`.
The pillars are `concepts`, `transactions`, `building`, and `security`.
Copy a [real task](../tasks/) with similar needs.

| Path | Purpose |
| --- | --- |
| `task.toml` | Harbor settings and metadata: pillar, motivation, and modes. |
| `instruction.md` | The instruction the agent receives. |
| `environment/` | A Dockerfile, starting files, and any declared sidecars. |
| `tests/` | The verifier, check data, and optional criteria. |
| `solution/solve.sh` | The solution that Harbor's oracle runs. |

Keep task-specific values inside the task folder.
Copy starting files through the Dockerfile.
Declare sidecars only when the task needs them.
Use `metadata.required_env` for required host variables.

Read [Free checks](harbor.md#free-checks) for image pins, check records, targets, Forge, criteria, and secret-gated tasks.
Read [Board jobs](harbor.md#board-jobs) for modes and the board-wide time limit.
The [runner reference](../runner/README.md#ci-and-publication) covers CI and publication.

From the repository root, run:

```sh
unset OPENROUTER_API_KEY ANTHROPIC_API_KEY OPENAI_API_KEY ANTHROPIC_AUTH_TOKEN EXA_API_KEY
uv run python scripts/ci.py images
uv run ethevals free-check --tasks tasks/PILLAR/NAME --output results/new-task
```

Use the task's actual path and a fresh output directory.
The oracle must pass every check, and nop must fail at least one check.
The free check skips paid criteria and reports missing secret variables before skipping their trials.
