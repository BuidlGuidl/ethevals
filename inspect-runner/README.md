# Runner reference

The Python package lives in `inspect-runner/ethevals/`.
The root `pyproject.toml` installs the `ethevals` command.

## Eval folders

An eval lives at `evals/<pillar>/<name>/`.
The pillar is `concepts`, `transactions`, `building`, or `security`.
The folder contains `eval.yaml`, `workspace/`, and `scorer/scorer.yaml`.
An optional `compose.yaml` declares services for an internet epoch.
Without it, the runner uses `images/stock.compose.yaml` for quizzes and builds.

`eval.yaml` requires `type`, `motivation`, `prompt`, and `modes`.
It accepts optional `choices`, a list of strings, and `time_limit`, a positive number of seconds.
Modes use the glossary names directly: `vanilla`, `internet`, and `skills`.
The runner selects only modes that each eval declares.
`run` defaults to vanilla. `check` selects vanilla for quizzes and internet for other types.
An eval without the selected mode is skipped. A selection with no eligible evals reports an error.
The internet mode supports Claude Code. The skills mode is not implemented.
The folder path supplies the eval ID and pillar.
Targets stay under `scorer/`.

`scorer/scorer.yaml` requires a `scorers` list, including for a single kind.
A target uses `scorers: [{kind: target, target: "8004"}]`.
A build can use `scorers: [{kind: tests}, {kind: rubric}]`.
Each kind appears once. Every emitted check must pass for the epoch to pass.
A target is a nonempty string or a list of nonempty strings. Any listed target can pass.
Vanilla quizzes allow only one target or a single-item list, because stock Inspect must preserve the exported answer.
Choices cannot contain blank or whitespace-only entries.
Quote numbers and hex addresses because YAML can read them as numbers.
Unknown keys and invalid values report their file and key.

The target scorer accepts these fields:

| Field | Values or default |
| --- | --- |
| `name` | Stable check name. Default `answer`. Lowercase letters, digits, and underscores. |
| `method` | `match`, `pattern`, or `choice`. Default `match`. |
| `location` | `begin`, `end`, `any`, or `exact`. Default `exact`. Used by `match`. |
| `ignore_case` | Default `true`. Used by `match` and `pattern`. |
| `numeric` | Default `false`. Used by `match`. |
| `pattern` | Required regex for the `pattern` method. |
| `reference` | Optional complete reference reply. Defaults to the first target, with `ANSWER:` for choice quizzes. |

A quiz with `choices` requires the `choice` method and letter targets, such as `C`.
The solver uses Inspect's `multiple_choice()` path without shuffled choices or chain-of-thought prompts.
Other vanilla quizzes use `generate()` without tools.
Internet quizzes send the same formatted question through Claude Code and use the same target scorer.
For `match` and `choice`, the reference check only proves that the target matches itself.
For example, `pattern: "ERC ([0-9]+)"` and `target: "8004"` need `reference: "ERC 8004"`.

The eval hash includes file paths and bytes, including new files that the author has not committed.
Outside `scorer/`, it excludes `.DS_Store`, `out`, `cache`, `lib`, `__pycache__`, and `.pytest_cache`.
These names are forbidden anywhere under `scorer/`.
The runner rejects symlinks before exclusions, including links nested inside ignored directories.
One validated file manifest supplies hashing, workspace contents, and every scorer input.
The runner captures the manifest's bytes at load time. Later source edits cannot change that epoch's inputs.
Other files count regardless of Git status. Custom `.gitignore` rules do not change this policy.
The hash excludes timestamps and permissions. Renames change it.

## Results rows

Each `rows.jsonl` file contains one flat JSON object per epoch.
The exporter replaces the file atomically after Inspect returns.
After an abrupt kill, the logs remain the recovery source until the next command exports rows.
The log store only grows. Retry logs never replace earlier logs.
Rows cover the whole store, with the latest row per eval ID, eval hash, agent, mode, and epoch number.
The agent consists of harness, model, and effort. Vanilla epochs have a null harness.
Mock answer kinds also distinguish identities so reference and empty answers cannot share results.
Prices, grader settings, and execution limits do not change an existing epoch's identity.
Their recorded values describe the execution that produced the row.
Changing a limit applies to missing epochs. A completed limit failure remains final.

Each scheduled epoch has one Inspect task with one sample and one Inspect epoch.
Task metadata holds the ETH Evals epoch number. `log_epoch` holds Inspect's epoch number.
This lets the runner select missing epochs without using Inspect's broader task identity.
`max_attempts` permits two executions per identity, including errors and interrupted executions recorded in logs.
After the second error, `run` returns failure without another model call.
Time and cost limits fail the existing checks with the limit reason. The row's `limit` field records the limit.
`check` writes fresh logs on every invocation and checks only the current selection.
The Python `run()` result also contains only the current selection. `rows.jsonl` contains the whole store.

| Fields | Meaning |
| --- | --- |
| `schema_version` | Results format version, currently `3`. |
| `eval_id`, `eval_hash`, `pillar`, `type` | Eval identity at execution time. |
| `harness`, `model`, `effort`, `mode` | Agent or bare model identity. A bare model has a null harness. |
| `harness_version`, `images` | Harness version and service image tags used for this execution. |
| `grader_model`, `grader_effort`, `grader_prices` | Grader identity and configured prices. Free checks bind the grader to mockllm. |
| `answer_kind` | `reference`, `empty`, or `default` for mock checks. Null for paid epochs. |
| `epoch`, `status`, `passed` | Epoch number and result. Errors have a null verdict. |
| `attempt`, `max_attempts` | Execution count and configured cap per identity. |
| `model_metered_usd`, `grader_metered_usd` | Dollars recorded by Inspect's cost meter for each role. Mock usage can have synthetic prices. |
| `cost_limit_usd`, `grader_cost_limit_usd`, `limit` | Separate budgets and any player limit that stopped execution. |
| `checks` | JSON object keyed by check name. Each check has `passed` and a one-line `reason`. |
| `error_kind`, `error_reason` | Error details, separate from a failed check. |
| `model_tokens`, `grader_tokens`, `total_tokens` | Total token counts. Grader usage is subtracted from overall usage. |
| `token_source` | `mock` or `provider`. Mock token counts are synthetic. |
| `model_cost_usd`, `model_cost_source`, `prices` | Model cost, its source, and the configured price object. Unknown cost is null with source `unavailable`. |
| `grader_cost_usd`, `grader_cost_source`, `grader_prices` | Separate grader cost, source, and price object. No grader calls means zero with source `no_usage`. |
| `working_seconds`, `total_seconds` | Inspect's working time and elapsed time. Setup failures can leave these null. |
| `log_file`, `log_sample_id`, `log_epoch`, `sample_uuid` | Log path relative to the results folder and Inspect's sample identity. |

The exporter reads complete logs so long reasons survive Inspect's summary truncation.
It uses `role_usage["grader"]` even when the grader and model under test share a model name.
Synthetic setup-failure rows have unknown costs for both roles.

## Site catalog

Run `uv run ethevals catalog --output site/.catalog` from the repository root to export public eval declarations.
The command uses the same loader and captured file manifest as execution and hashing.
`catalog.json` contains declarations, eval IDs, pillars, and hashes. It excludes scorer contents and workspace files.
The site's normal build runs this command and reads schema v3 rows. See [the site README](../site/README.md).

## Extension hooks

`SCORERS` in `scorers.py` owns each kind's schema, validation, sample fields, reference reply, and scorer factory.
A new kind returns an Inspect `Score` with `metadata["checks"]`.
Each named check requires a boolean `passed` and a nonempty `reason`.
`named_checks()` normalizes each reason to one line and passes the epoch only when all checks pass.

`CHECK_SOLVERS` in `checks.py` maps each eval type to its free-check factory.
A factory returns a `CheckRun` with a solver and a mock reply.
The build factory copies `scorer/solution/` for the reference case.
The empty case leaves the workspace untouched.
Both cases retain the task, scorer registry, log, and results exporter.
The rubric registry entry sets `free_check=False` and stays out of free checks.

`AGENTS` in `agents.py` owns agent solver factories. Step 3 can add Codex CLI and OpenCode there.
`actors.py` constructs the player and grader once, with their models, effort, and prices.
`build_task()` receives these actors. Check-only solvers and delays live in `checks.py`.
`Eval.sample()` already maps workspace files to `/workspace/` and keeps scorer files separate.
Vanilla execution clears the file mapping before a plain model call.
Internet execution sets a Docker sandbox on each sample.

`config.yaml` holds model names, default effort, and the fixed grader selection.
Effort accepts `none`, `minimal`, `low`, `medium`, `high`, `xhigh`, or `max`.
`validate` rejects other effort values before a paid run.
It also rejects harness names absent from `AGENTS`. A null harness supports vanilla mode only.
Only Opus currently declares a harness. The other configured models remain available for vanilla quizzes.
`agent_model_config` supplies the harness's model description.
`register_prices()` registers model information before use, including names absent from Inspect's database.
`search_provider` holds the Exa MCP URL. A null value disables that MCP server.
`time_limit` supplies the fallback limit. `time_limits` sets limits by eval type.
An eval's `time_limit` takes precedence. It remains the main bound on a hung agent.
`cost_limit` gives the player $5. `grader_cost_limit` gives the rubric grader $0.50 across all its questions and retries.
Both settings live in `config.yaml`, alongside `max_attempts: 2`.
Inspect uses the configured prices for uncached input, cache reads, cache writes, and output.
It checks cost after each call. An in-flight call can exceed its remaining budget.
Each grader call has a 1,024-output-token limit and a 60-second attempt timeout.
`max_tasks` and `max_samples` control concurrency. Both default to four.

## Build scoring

Tests live in `scorer/tests/`. Build and act evals require `scorer/solution/`.
The runner stops the agent user's processes with SIGSTOP before collecting one snapshot into a fresh root-owned path.
It checks that those processes have stopped. PID 1 remains available to reap processes during container cleanup.
Forge and the rubric receive the same captured files. Neither scorer reads the live workspace again.
The runner rejects archive links, unsafe paths, and special files.
The archive is limited to 50 MiB of file contents and 20,000 files.
Only `.sol` files under `src/` and `lib/` enter the scorer workspace.
Submitted `lib/openzeppelin-contracts/` and `lib/forge-std/` copies never enter it.
The image supplies OpenZeppelin 5.4.0 and forge-std 1.9.7 from `/opt/ethevals/lib/`, owned by root.
The forge-std pin is `77041d2ce690e692d6e03cc812b57d1ddaa4d505`.
The runner adds the eval's tests and its own `images/foundry.toml` there.
It also supplies that configuration to the agent and states the grading rule in the prompt.
Authors can use the `@openzeppelin/contracts/` and `forge-std/` remappings.
Other dependencies require relative imports under `src/` or `lib/`. Grading ignores submitted remappings and compiler settings.
The config uses automatic compiler selection with network access, FFI disabled, and no filesystem permissions.
Agent test directories and cached output do not enter the scorer workspace.
Forge runs with a clean environment, `ffi = false`, and no filesystem cheatcode permissions.
The agent and scorer have separate filesystems with no shared volumes.

The scorer first runs the eval's reference solution in the scorer container.
Its test functions define `forge:<test path>:<suite>:<function signature>` checks. `forge:compile` always accompanies them.
The reference must pass. A broken reference produces an infrastructure error and requires an eval fix.
Forge runs only tests under `test/`. Agent functions outside that expected set cannot add checks.
Compilation failure fills every Forge check with the compiler reason. A setup failure fills that suite's missing tests.
Workspace failures fail all the eval's Forge and rubric checks with the snapshot reason.
The fixed set keeps the same denominator across successful and failed submissions.
Free checks omit rubric questions; paid epochs include them.

`scorer/rubric.md` has one `## stable_name` heading per question, followed by its yes-or-no question.
Each question becomes `rubric:stable_name`, independent of its position in the file.
The grader receives the submitted Solidity files used by Forge, including other dependencies under `lib/`.
It excludes the image's runner-owned dependencies and tells the grader where those dependencies come from.
It skips files above 100,000 bytes or beyond a 300,000-byte total, then considers smaller later files.
Every omitted file appears in the grader request. Incomplete evidence always fails the rubric checks.
It receives no tools and must return a boolean `passed` and a one-line `reason` in JSON.
The request uses a structured response schema. The parser also accepts JSON inside prose or Markdown fences.
Each question permits two calls. Invalid replies or failed requests retry only the grader and then fail that question.
Grader budget exhaustion fails the rubric checks. It cannot trigger another agent epoch.
Grader calls use Inspect's `grader` role for separate token and cost accounting.

## Compose rules

Custom compose files use prebuilt images and declare `default` and `scorer` services.
Those two services require the stock runner image and its unprivileged `agent` user.
Other services can choose their own images. This keeps process control and runner-owned dependencies outside the eval author's control.
All services join the `private` network with `internal: true`.
Only `default` and `scorer` also join the `internet` network.
No service publishes host ports. Privileged mode, host namespaces, host paths, and external volumes are rejected.
The agent and scorer cannot mount volumes. Other services can use declared private named volumes.
Custom Docker builds are rejected because their contexts can include scorer files.
Stock image builds use the runner-owned `images/` directory as their context.
Host environment inheritance is rejected. Service environment values must be explicit.
Decoded YAML values cannot contain `$VAR` or `${VAR}` substitutions. `$$` remains a literal dollar sign.
The agent and scorer cannot override loader or shell startup environment variables, which also affect privileged collection commands.

Step 4 can add chain images and private services without changing the agent solver.
It still needs service setup and act reference preparation. No setup script runs in this step.

The [paid ADR test](../README.md#run-the-paid-adr-0002-test) gives exact commands and expected row fields.

## Export and publish commands

From the repository root, export vanilla quizzes with `uv run ethevals export-hf --output out/hf`.
The output directory must be empty. `--hf-repo` and `--license` set the dataset card values.
Run the offline proof with `uv run ethevals prove-hf --export out/hf --output out/hf-proof`.
The proof records observed scores from stock Inspect and the runner in `out/hf-proof/report.json`.

Plan log publication with:

```sh
uv run ethevals publish-logs --output results/paid \
  --repo OWNER/REPO --run-id RUN_ID --commit FULL_SOURCE_SHA --dry-run
```

The dry run writes nothing. Replace `--dry-run` with `--publish` to upload through `gh`.
After success, the command writes `results/paid/published/results-RUN_ID.jsonl`.
It skips hidden rows and logs already linked to releases. Keep publication files when reusing a results folder.
Each command accepts only its own flags. Export, proof, and publish commands require explicit output paths.
`validate` rejects alternative targets and extra scorers on vanilla quizzes.
