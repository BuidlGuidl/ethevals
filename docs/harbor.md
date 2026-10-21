# Harbor tasks

## Board jobs

`runner/ethevals/job.yaml` holds the board's agents, models, CLI pins, Harbor pin, and time limit.
Each agent entry names a Harbor agent or Python import path and a model key.
Its `paid_by` field is `plan`, `api_key`, or `free` for a local stand-in.
Model effort becomes Harbor's `reasoning_effort`; `kwargs` carries other agent options.
Each entry's `env` passes through Harbor's agent environment.
The shipped plan entries set their force flags there, so local and CI trials select the same payment source.
`required_env` lists nonempty credential variables; `required_files` lists credential paths, with Harbor's `${VAR:-default}` substitution.
The runner checks these requirements before creating any Harbor job.
An entry's `modes` defaults to `[internet]`.
The planner intersects those modes with the job selection and each task's modes.
Skills mode uploads the repo's captured skills pack through Harbor.
Harbor registers the pack in the selected agent's skill directory.
The same captured bytes supply the skills hash and every skills trial in the command.
Snapshots stay under `OUTPUT/skills/HASH/` beside the jobs that use them.

```sh
uv run ethevals plan --modes internet --trials 1 --budget 100
uv run ethevals run --modes internet --trials 1 --budget 100 --output results/local
```

Vanilla entries use `ethevals.vanilla:VanillaAgent` and declare `modes: [vanilla]`.
They use API keys, regardless of how an internet entry pays for the same model.
The agent sends the instruction in one API call through Harbor's LiteLLM dependency, with no tools or environment access.
It disables request retries; the job's attempt limit still applies.
Its `kwargs.completion` accepts provider options such as `api_base` and `max_tokens`.
Model names and effort come from the same model settings as internet entries.
Vanilla rows have `agent: null` and appear in the knowledge table.

Every missing agent trial requires an explicit `--budget`, including free stand-ins and plan-funded trials.
API-key trials reserve `cost_limit_usd` for each remaining attempt.
Plan-funded trials reserve $0 of agent spend.
The reserve controls admission.
For agents whose Harbor options include `max_budget_usd`, the runner sets that cap from `cost_limit_usd`.
Claude Code exposes this flag; other agents have no runtime spending cap.
Planning needs no provider keys or Docker.
Use `--tasks`, `--agents`, and `--models` to select entries.
Use `--trial N` with one task, agent, and mode to run one numbered trial.
Completed passes and failures never repeat for the same task hash, agent, model, effort, mode, and trial number.
Skills trials also include the skills hash in their identity.
Internet and vanilla trials record `skills_hash: null`, so a skill edit repeats only skills trials.
Agent errors repeat up to `max_attempts`; `--retry-errors` grants one further agent attempt per selected error.

Run the same command and output directory after an interruption.
The runner reads saved Harbor trial folders before planning and rebuilds missing rows.
Each numbered trial has its own Harbor job under `OUTPUT/jobs/`.
`board.json` records that trial's board identity and payment source beside Harbor's files.
Rows use schema version 7 and link a trajectory JSON file when one exists.
Cost comes from Harbor's API-price usage record, regardless of the payment source.
Unknown cost stays null; free stand-ins cost $0.
Rows record judge model, effort, API-price cost, and payment source separately.
The free check still skips paid criteria.

To open a local job on the board, build from `site/`:

```sh
ETHEVALS_ROWS=../results/local/rows.jsonl pnpm build
```

The build copies local trajectories into the static export and links published trajectories directly.

## Free checks

Harbor is pinned to 0.24.0 in `pyproject.toml` and `uv.lock`.
This version copies declared trajectories into a separate verifier after the agent stops.
The verifier can read the final reply without changing the instruction or asking for an answer file.
The oracle and nop runs exercise this path before a version change can pass.

Run the free check from the repository root:

```sh
unset OPENROUTER_API_KEY ANTHROPIC_API_KEY OPENAI_API_KEY ANTHROPIC_AUTH_TOKEN EXA_API_KEY
uv run python scripts/ci.py images
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
The shared quiz image ships `/opt/target_checks.py`.
Call it with `/tests/target.json` from `tests/test.sh`.
The JSON holds `name` and `target`, which accepts one string or a list of accepted strings.
`location` accepts `exact`, `begin`, `end`, or `any`; it defaults to `exact`.
The helper trims punctuation around the reply and ignores case unless `ignore_case` is false.
It writes the named check and reward, without copying a reply reader into each task.

Tasks declare sidecars in `environment/docker-compose.yaml`.
Single-container tasks use `environment/Dockerfile` alone.
Each task Dockerfile starts from a pinned shared GHCR image and copies its starting files from its own folder.
Compose build contexts stay inside the task folder.
Keep starting files as plain files; copy them with `COPY` rather than creating them in a Compose command.
The lint checks shared image pins against their build inputs.
After changing a shared image input, run `uv run python -m ethevals.images.tag` and update the affected task pins.
`scripts/ci.py images` builds those tags locally. `--publish` pushes both Linux architectures to GHCR.
The shared chain image runs setup before its healthcheck releases the agent.
Setup writes `chain_context.json` on a read-only public volume.
It writes `private_chain_context.json` in a root-only directory on a separate volume.
The agent runs as `agent`. The shared verifier runs as root and reads the live chain.
Only the filtered RPC listens outside the sidecar's loopback interface.

Tasks list required secret variable names in `metadata.required_env` in `task.toml`.
If a variable is unset, the free check lints the task and skips its runs.
The planner defers its pending trials and excludes them from the budget and CI matrix.
Both commands print the missing variable's name.
Compose interpolation accepts only declared variable names.
Compose service keys use an allowlist; host namespaces, extra capabilities, and implicit host environment values are forbidden.
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
After Harbor saves the tests, RewardKit answers these questions from the ATIF trajectory and the task's declared `artifacts`.
Artifact destinations follow Harbor's paths under the trial's `artifacts/` directory.
Missing artifacts or trajectories produce a judge error.
The board combines test checks and criteria checks; every check must pass.
Criteria headings must differ from test check names.
The judge's model, effort, time limit, payment source, and admission reserve come from the job config's `judge` settings.
The default judge uses Opus 5.5 through `ANTHROPIC_API_KEY`; it refuses plan tokens.
Each agent attempt reserves two judge attempts at `cost_limit_usd` each, even when a plan pays for the agent.
RewardKit is pinned to 0.2.3, which supports Harbor's ATIF trajectory input and per-question reasons.
`verifier/judge.json` preserves its output, usage, reasons, and errors beside Harbor's test records.
Row recovery reads that file without another judge call.
Judging retries on the saved trial folder, up to two attempts, without another agent run.
`judge.json` counts attempts before starting them, including an interrupted attempt, and adds their known costs.
After an interruption, the next run reserves only the remaining judge attempts and keeps the agent attempt number.
Two unsuccessful attempts leave a judge error on the board.
An exhausted judge or an unavailable saved folder cannot start another agent attempt.
Timeouts, invalid answers, and missing reasons count as judge errors, so they never become failed checks.
Local stand-ins set `judge.paid_by: free` and use a local model endpoint.
The free check prints a skip note because the judge needs a paid API call.

Pull-request CI calls the free check through `scripts/ci.py checks`.

## Dataset publication

`uv run python scripts/ci.py release --output out/hf --license mit` stages every task and previews the HF upload.
`uv run ethevals export-hf --output out/hf` stages the same layout without an upload preview.
Both commands require an empty output directory.
The export copies every task file unchanged, including setup, tests, and solutions.
Published folder names combine the pillar and task name under `tasks/`.
Harbor 0.24.0 discovers immediate children there when `--repo` has no dataset selector.
`registry.json` also supplies the explicit `ethevals@1.0` dataset entry.
This version names the registry format; pin the repository revision to select task content.

```sh
harbor run --repo https://huggingface.co/datasets/buidlguidl/ethevals-test --agent oracle --n-concurrent 1
```

Select a task with `--include-task-name NAME` and set its declared `metadata.required_env` variables first.
Replace `oracle` with `nop` to check untouched work.
The folder needs Docker and Harbor, with no ETH Evals install.
Plain Harbor runs execute the task's verifier; the board also runs declared paid criteria through RewardKit.

On `main`, the release workflow pushes the shared images before uploading the dataset with `HF_TOKEN`.
The upload removes obsolete files under `tasks/` and the old quiz `data/` folder in the same commit.
Files outside those managed folders remain unless the staged output replaces them.
It checks image access with an empty Docker credential directory before the dataset upload.
GHCR creates new packages as private, even for public repositories.
After each package's first push, an owner must set its visibility to public in GitHub Packages and rerun the workflow.
It tags HF revisions `gh-SHORT_SHA` and supports manual reruns on `main`.
Pull requests build the same image tags locally and publish nothing.

References: [Harbor v0.24.0](https://github.com/harbor-framework/harbor/tree/v0.24.0),
[separate verifier inputs](https://docs.harborframework.com/tasks/separate-verifier).
