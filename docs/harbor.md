# Harbor tasks

## Board jobs

`runner/ethevals/job.yaml` holds the board's agents, models, CLI pins, and Harbor pin.
Each agent entry names a Harbor agent or Python import path and a model key.
Its `paid_by` field is `plan`, `api_key`, or `free` for a local stand-in.
Model effort becomes Harbor's `reasoning_effort`; `kwargs` carries other agent options.
Each entry's `env` passes through Harbor's agent environment.
The board sets no agent or verifier time limit.
Harbor defaults to no agent limit and a 600-second verifier limit.
Set `[agent].timeout_sec` or `[verifier].timeout_sec` in `task.toml` only when the task needs a limit.
Rows show the limit Harbor reached, and an agent timeout still checks the work left behind.
CI stops each trial step after 190 minutes.
Locally, a stuck agent with no budget flag can run without a bound.
The shipped plan entries set their force flags there, so local and CI trials select the same payment source.
`required_env` lists nonempty credential variables.
Each `required_files` entry declares a `path` and a `policy`, with Harbor's `${VAR:-default}` substitution in the path.
The `plan_tokens` policy requires JSON with `auth_mode = "chatgpt"` and a nonempty `tokens.access_token`.
The agent's environment overrides the host when selecting the credential file.
Every plan entry must declare a credential requirement.
The runner checks these requirements before creating any Harbor job.
An entry's `modes` defaults to `[internet]`.
The planner intersects those modes with the job selection and each task's modes.
Skills mode uploads the repo's captured skills pack through Harbor.
Harbor registers the pack in the selected agent's skill directory.
The same captured bytes supply the skills hash and every skills trial in the command.
Snapshots stay under `OUTPUT/skills/HASH/` beside the jobs that use them.

```sh
uv run ethevals plan --modes internet --n-attempts 1 --budget 100
uv run ethevals run --modes internet --n-attempts 1 --budget 100 --output results/local
```

Vanilla entries use `ethevals.vanilla:VanillaAgent` and declare `modes: [vanilla]`.
They use API keys, regardless of how an internet entry pays for the same model.
The agent sends the instruction in one API call through Harbor's LiteLLM dependency, with no tools or environment access.
It disables request retries; the job's retry limit still applies.
Its `kwargs.completion` accepts provider options such as `api_base` and `max_tokens`.
Model names and effort come from the same model settings as internet entries.
Vanilla rows have `agent: null` and appear in the knowledge table.

Every missing agent trial requires an explicit `--budget`, including free stand-ins and plan-funded trials.
API-key trials reserve `cost_limit_usd` for the initial execution and each remaining retry.
Plan-funded trials reserve $0 of agent spend.
The reserve controls admission.
For API-key entries whose Harbor options include `max_budget_usd`, the runner sets that cap from `cost_limit_usd`.
The runner sets no spending cap for plan entries.
Set `cost_limit_usd` outside `kwargs`; the config rejects `kwargs.max_budget_usd` on agents and models.
Claude Code exposes this flag; other agents have no runtime spending cap.
Planning needs no provider keys or Docker.
Use `--tasks`, `--agents`, and `--models` to select entries.
Use `--trial N` with one task, agent, and mode to run one numbered trial.
Completed passes and failures never repeat for the same task hash, agent, model, effort, mode, and trial number.
Skills trials also include the skills hash in their identity.
Internet and vanilla trials record `skills_hash: null`, so a skill edit repeats only skills trials.
`n_attempts` counts scored trials per task, agent, and mode; `--n-attempts N` overrides it.
Retries add no scored trials.
`retry.max_retries` caps reruns after errors, with a default of 1.
Harbor's `RetryConfig` supplies the exception exclusions and optional inclusion filter.
Excluded errors never start another agent execution.
The board schedules retries across jobs and admits their spend before execution.
Rows count retries from zero for the initial execution.
The plan lists agent trials under `missing` and holds judge errors under `exhausted_errors`.
Judge errors never schedule another agent execution, even after artifacts move.
Duplicate check names cause a verification error.

Run the same command and output directory after an interruption.
The runner reads saved Harbor trial folders before planning and rebuilds missing rows.
Each numbered trial has its own Harbor job under `OUTPUT/jobs/`.
`board.json` records that trial's board identity and payment source beside Harbor's files.
Rows use schema version 8 and link a trajectory JSON file when one exists.
They retain all reward dimensions; `reward == 1` supplies the test pass bit.
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
Each task has a `[task]` table with a unique `buidlguidl/NAME`, a description, authors, and keywords.
Lint requires the name and a nonempty description.
Pillar and modes stay in `[metadata]`.
It then runs Harbor's oracle and nop agents, one trial at a time.
Use `--tasks` to select task folders.
`uv run ethevals lint` runs the lint alone.

Test tools can write `/logs/verifier/checks.json`:

```json
{"check_name": {"passed": true, "reason": "A one-line reason."}}
```

`test.sh` copies `/opt/check_records.py` into `/tests/`, then runs `rewardkit /tests`.
That shared criterion turns each record into a named RewardKit check with its reason.
Each task's `reward.toml` sets `all-pass` for the record file and the root `reward`.
RewardKit 0.2.3 ships in both shared images and needs no network for programmatic checks.
The chain image caches Solidity 0.8.30 at build time; tasks can install other compilers in their images.
RewardKit alone writes `reward.json` and `reward-details.json` under `/logs/verifier/`.
Rows and free checks read those files; additional reward dimensions remain available.
The free check requires every oracle check to pass and at least one nop check to fail.
Both runs must report the same check names.
Missing records, execution errors, or rewards that disagree with checks fail the command.

Quiz verifiers read the last assistant message in `/logs/agent/trajectory.json`, using Harbor's ATIF format.
The task declares that path in `artifacts` so the separate verifier receives it.
The solution writes a stand-in trajectory for Harbor's oracle agent.
The nop agent leaves no reply.
The shared quiz image ships `/opt/target_checks.py`.
Import it from a Python criterion file under `/tests/`, with `/opt` on `sys.path`.
Call `rk.final_answer(accepts, name="check_name")` with the task's answer rule.
The rule accepts the final reply and returns a boolean.
The shared criterion supplies the empty-reply check and the reason.
Answers and matching rules stay inside each task.

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

Each task's compose file declares host variables through `${VAR:?message}` interpolation.
Compose stops with that message if the value is missing or empty.
If a variable is unset, the free check lints the task and skips its runs.
The planner defers its pending trials and excludes them from the budget and CI matrix.
Both commands print the missing variable's name.
Tasks cannot request credential names from the job's agent requirements, agent environment, or judge key.
Use `--config` with lint or free-check to check against another job config.
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

Criteria live in RewardKit judge TOML files under `tests/` and run through `test.sh`.
Lint requires named binary criteria, `atif-trajectory = "/logs/agent/trajectory.json"`, and `guard = "flag"` or `"penalize"`.
Each judge and its enclosing rewards use `all-pass`, so every test and criterion counts toward the same reward.
The task's judge model and effort provide the defaults for plain Harbor runs.
The board overrides them through `REWARDKIT_JUDGE` and `REWARDKIT_REASONING_EFFORT` from the job config.
Each judged task declares only `ANTHROPIC_API_KEY = "${ANTHROPIC_API_KEY}"` in `[verifier.env]`.
A missing key stops Harbor with the variable's name.
Use a judge-only API key with its own spend limit.
Harbor scopes agent credentials to agent commands; verifier commands receive no plan token.
The board refuses a plan token in the judge key before starting Harbor.
For shared verifiers, the judge key reaches the agent's container after the agent stops.
Processes the agent left running can still read it, as ADR 0011 records.
Each agent execution reserves three calls per judge batch, multiplied by samples and `cost_limit_usd`.
In individual mode, the reserve covers each criterion and its separate guard call.
Executions paid by a plan also reserve judge spend.
`reward-details.json` supplies criterion reasons, errors, and API-price judge usage to rows.
A missing cost stays null; local stand-ins use `judge.paid_by: free` and cost $0.
RewardKit retries malformed replies internally up to three calls.
Timeouts recorded on criteria or guards produce a judge error on the board.
Malformed replies stop the verifier and produce a Harbor trial error.
Neither error silently starts another agent execution.

For saved tasks whose verifier needs only copied artifacts, use `harbor trial regrade TRIAL -p TASK`.
Harbor regrade uses a separate verifier and leaves the source trial untouched.
It cannot restore a sidecar's live state, so it cannot repeat a chain task's Forge tests.
For those tasks, use the [explicit recovery command](../runner/README.md#ci-and-publication) after reviewing its budget.
The board performs no automatic regrade and no automatic agent retry for judge errors.

The free check stages task copies under `OUTPUT/tasks/`, removes judge TOMLs, and overrides the judge key with an empty value.
The copies drop aggregation weights and empty judge groups; `all-pass` still requires every remaining test.
It prints the skipped-criteria note and runs the unchanged programmatic tests through RewardKit.
Source tasks and published folders keep their judges and required keys.

Pull-request CI calls the free check through `scripts/ci.py checks`.

## Dataset publication

`uv run python scripts/ci.py release --output out/hf --license mit` stages every task and previews the HF upload.
`uv run ethevals export-hf --output out/hf` stages the same layout without an upload preview.
Both commands require an empty output directory.
The export copies exactly the files Harbor's packager counts, with their bytes unchanged.
The board's task hash is Harbor's `sha256:` package digest.
Saved board trials must carry the same digest in `lock.json` as their plan.
Published folders combine the pillar and directory name under `tasks/`.
Registry entries use `[task].name`, which Harbor also reads from the copied task.
Harbor 0.24.0 discovers immediate children there when `--repo` has no dataset selector.
`registry.json` also supplies the explicit `ethevals@1.0` dataset entry.
This version names the registry format; pin the repository revision to select task content.

```sh
harbor run --repo https://huggingface.co/datasets/buidlguidl/ethevals-test --agent oracle --n-concurrent 1
```

Select a task with `--include-task-name NAME` and set the host variables its compose file names first.
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
