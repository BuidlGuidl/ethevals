# Harbor tasks

Harbor is pinned to 0.24.0 in `pyproject.toml` and `uv.lock`.
This version copies declared trajectories into a separate verifier after the agent stops.
The verifier can read the final reply without changing the instruction or asking for an answer file.
The oracle and nop runs exercise this path before a version change can pass.

Run the free check from the repository root:

```sh
unset OPENROUTER_API_KEY ANTHROPIC_API_KEY OPENAI_API_KEY ANTHROPIC_AUTH_TOKEN EXA_API_KEY
uv run ethevals free-check --output results/free-check
```

Use a fresh output directory for each job.
The command lints every folder under `tasks/` that contains `task.toml`.
It then runs Harbor's oracle and nop agents, one trial at a time.
Use `--tasks` to select task folders.
`uv run ethevals lint` runs the lint alone.

Each verifier writes `/logs/verifier/checks.json`:

```json
{"check_name": {"passed": true, "reason": "A one-line reason."}}
```

It also writes `reward.txt`, with 1 when every check passes and 0 otherwise.
The free check requires every oracle check to pass and at least one nop check to fail.
Both runs must report the same check names.
Missing records, execution errors, or rewards that disagree with checks fail the command.

Quiz verifiers read the last assistant message in `/logs/agent/trajectory.json`, using Harbor's ATIF format.
The task declares that path in `artifacts` so the separate verifier receives it.
The solution writes a stand-in trajectory for Harbor's oracle agent.
The nop agent leaves no reply.

Pull-request CI calls the free check through `scripts/ci.py checks`.
The existing Inspect free check covers folders that remain under `evals/` during the move.

References: [Harbor v0.24.0](https://github.com/harbor-framework/harbor/tree/v0.24.0),
[separate verifier inputs](https://docs.harborframework.com/tasks/separate-verifier).
