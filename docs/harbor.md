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

Tasks declare sidecars in `environment/docker-compose.yaml`.
The shared chain image runs setup before its healthcheck releases the agent.
Setup writes `chain_context.json` on a read-only public volume.
It writes `private_chain_context.json` in a root-only directory on a separate volume.
The agent runs as `agent`. The shared verifier runs as root and reads the live chain.
Only the filtered RPC listens outside the sidecar's loopback interface.

Tasks list required secret variable names in `metadata.required_env` in `task.toml`.
If a variable is unset, the free check lints the task and skips its runs.
It prints the missing variable's name.
The task's compose file passes each secret only to the sidecar that needs it.
A fork's sidecar sets `FORK_RPC_URL` and `FORK_BLOCK_NUMBER` for Anvil.
Setup and the agent receive no upstream URL.
The chain discards Anvil output. Startup failures report a generic error.
The manual fork-check workflow requires these variables before it starts oracle and nop runs.
It checks the reviewed commit and posts the result as that commit's `fork check` status.

Forge verifiers call `python3 /opt/forge_checks.py` from `tests/test.sh`.
The helper copies the agent's files and tests into a fresh project.
It disables FFI and scopes library remappings to each agent project.
It writes `compile` and each test's check, with contract names for failing setup and constructors.
Compiler download failures raise errors instead of failed checks.
The helper keeps Forge stdout and stderr beside `checks.json`.

Criteria live in `tests/criteria.md`.
Each `##` heading names a check and the following text asks a yes-or-no question.
The free check prints a skip note because the judge needs a paid API call.

Pull-request CI calls the free check through `scripts/ci.py checks`.

References: [Harbor v0.24.0](https://github.com/harbor-framework/harbor/tree/v0.24.0),
[separate verifier inputs](https://docs.harborframework.com/tasks/separate-verifier).
