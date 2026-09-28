# Runner reference

The Python package lives in `inspect-runner/ethevals/`.
The root `pyproject.toml` installs the `ethevals` command.

## Eval folders

An eval lives at `evals/<pillar>/<name>/`.
The pillar is `concepts`, `transactions`, `building`, or `security`.
The folder contains `eval.yaml`, `workspace/`, and `scorer/scorer.yaml`.
An optional `compose.yaml` declares services for an internet epoch.
Without it, the runner uses a complete stock compose file for the eval's type.

`eval.yaml` requires `type`, `motivation`, `prompt`, and `modes`.
It accepts optional `choices`, a list of strings, and `time_limit`, a positive number of seconds.
Modes use the glossary names directly: `vanilla`, `internet`, and `skills`.
The runner selects only modes that each eval declares.
`run` defaults to vanilla. `check` selects vanilla for quizzes and internet for other types.
An eval without the selected mode is skipped. A selection with no eligible evals reports an error.
The internet mode supports Claude Code. The skills mode is not implemented.
The folder path supplies the eval ID and pillar.
Targets stay under `scorer/`.

For one target scorer, `scorer/scorer.yaml` accepts `kind: target` and `target`.
To combine kinds, use `scorers: [{kind: tests}, {kind: rubric}]`.
Each kind appears once. Every emitted check must pass for the epoch to pass.
A target is a nonempty string or a list of nonempty strings. Any listed target can pass.
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
It excludes `.DS_Store`, `out`, `cache`, `lib`, `__pycache__`, and `.pytest_cache` at every depth.
These names are reserved for local artifacts and also appear in the repository's ignore rules.
The workspace file mapping uses the same exclusions, so ignored files never reach the agent.
Other files count regardless of Git status. Custom `.gitignore` rules do not change this policy.
The hash excludes timestamps and permissions. Renames change it. Symlinks outside excluded paths are rejected.

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
Environment errors run again. Time and token limits add a `runner_<type>_limit` failed check.
`check` writes fresh logs on every invocation and checks only the current selection.
The Python `run()` result also contains only the current selection. `rows.jsonl` contains the whole store.

| Fields | Meaning |
| --- | --- |
| `schema_version` | Results format version, currently `2`. |
| `eval_id`, `eval_hash`, `pillar`, `type` | Eval identity at execution time. |
| `harness`, `model`, `effort`, `mode` | Agent or bare model identity. A bare model has a null harness. |
| `grader_model`, `grader_effort`, `grader_prices` | Grader identity and configured prices. Free checks bind the grader to mockllm. |
| `answer_kind` | `reference`, `empty`, or `default` for mock checks. Null for paid epochs. |
| `epoch`, `status`, `passed` | Epoch number and result. Errors have a null verdict. |
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

## Extension hooks

`SCORERS` in `scorers.py` owns each kind's schema, validation, sample fields, reference reply, and scorer factory.
A new kind returns an Inspect `Score` with `metadata["checks"]`.
Each named check requires a boolean `passed` and a nonempty `reason`.
`named_checks()` normalizes each reason to one line and passes the epoch only when all checks pass.

`CHECK_SOLVERS` in `runner.py` maps each eval type to its free-check factory.
A factory returns a `CheckRun` with a solver and a mock reply.
The build factory copies `scorer/solution/` for the reference case.
The empty case leaves the workspace untouched.
Both cases retain the task, scorer registry, log, and results exporter.
The rubric registry entry sets `free_check=False` and stays out of free checks.

`AGENTS` in `agents.py` owns agent solver factories. Step 3 can add Codex CLI and OpenCode there.
`Eval.sample()` already maps workspace files to `/workspace/` and keeps scorer files separate.
Vanilla execution clears the file mapping before a plain model call.
Internet execution sets a Docker sandbox on each sample.

`config.yaml` holds model names, default effort, and the fixed grader selection.
Effort accepts `none`, `minimal`, `low`, `medium`, `high`, `xhigh`, or `max`.
`validate` rejects other effort values before a paid run.
`register_prices()` registers model information before use, including names absent from Inspect's database.
`search_provider` holds the Exa MCP URL. A null value disables that MCP server.
`time_limit` supplies the fallback limit. `time_limits` sets limits by eval type.
An eval's `time_limit` takes precedence. `token_limit` caps each epoch's total input and output tokens.
`max_tasks` and `max_samples` control concurrency. Both default to four.

## Build scoring

Tests live in `scorer/tests/`. Build and act evals require `scorer/solution/`.
The runner reads a tar archive from the finished agent workspace and rejects links, unsafe paths, and special files.
The archive is limited to 50 MiB of file contents and 20,000 files.
Only `.sol` files under `src/` and `lib/` enter the scorer workspace.
The runner adds the eval's tests and its own `images/foundry.toml` there.
Agent tests, compiler configuration, and cached output do not enter that workspace.
Forge runs with a clean environment, `ffi = false`, and no filesystem cheatcode permissions.
The agent and scorer have separate filesystems with no shared volumes.

Each Forge function becomes `forge:<test path>:<suite>:<function signature>`.
Failures keep the revert or assertion reason. A compiler error becomes `forge:compile` with the first diagnostic.
Infrastructure failures produce error rows, so the next command retries them.
An empty test result fails the `forge:tests` check.

`scorer/rubric.md` has one `## stable_name` heading per question, followed by its yes-or-no question.
Each question becomes `rubric:stable_name`, independent of its position in the file.
The grader receives UTF-8 workspace files, excluding `lib/`, `out/`, `cache/`, `.git/`, and `node_modules/`.
It skips files above 100,000 bytes and stops adding files at 300,000 bytes total.
It receives no tools and must return a boolean `passed` and a one-line `reason` in JSON.
Malformed grader replies produce error rows. Grader calls use Inspect's `grader` role for separate token and cost accounting.

## Compose rules

Custom compose files use prebuilt images and declare `default` and `scorer` services.
All services join the `private` network with `internal: true`.
Only `default` and `scorer` also join the `internet` network.
No service publishes host ports. Privileged mode, host namespaces, host paths, and external volumes are rejected.
The agent and scorer cannot mount volumes. Other services can use declared private named volumes.
Custom Docker builds are rejected because their contexts can include scorer files.
Stock image builds use the runner-owned `images/` directory as their context.
Host environment inheritance is rejected. Service environment values must be explicit.

Step 4 can add chain images and private services without changing the agent solver.
It still needs service setup and act reference preparation. No setup script runs in this step.

The [paid ADR test](../README.md#run-the-paid-adr-0002-test) gives exact commands and expected row fields.
