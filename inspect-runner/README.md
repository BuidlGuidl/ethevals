# Runner reference

The Python package lives in `inspect-runner/ethevals/`.
The root `pyproject.toml` installs the `ethevals` command.

## Eval folders

An eval lives at `evals/<pillar>/<name>/`.
The pillar is `concepts`, `transactions`, `building`, or `security`.
The folder contains `eval.yaml`, `workspace/`, and `scorer/scorer.yaml`.
An optional `compose.yaml` declares services for a future agent epoch.
Step 2a hashes that file but does not run or check its services.

`eval.yaml` requires `type`, `motivation`, `prompt`, and `modes`.
It accepts optional `choices`, a list of strings.
Modes use the glossary names directly: `vanilla`, `internet`, and `skills`.
The runner selects only modes that each eval declares.
`run` defaults to vanilla. `check` selects vanilla for quizzes and internet for other types.
An eval without the selected mode is skipped. A selection with no eligible evals reports an error.
Paid internet and skills execution remains part of step 2b.
The folder path supplies the eval ID and pillar.
Targets stay under `scorer/`.

For a target scorer, `scorer/scorer.yaml` requires `kind: target` and `target`.
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
Other quizzes use `generate()` without tools.
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

`SCORERS` in `scorers.py` maps each kind to its declaration schema and scorer factory.
A new kind returns an Inspect `Score` with `metadata["checks"]`.
Each named check requires a boolean `passed` and a nonempty `reason`.
`named_checks()` normalizes each reason to one line and passes the epoch only when all checks pass.

`CHECK_SOLVERS` in `runner.py` maps each eval type to its free-check solver factory.
Step 2b can register a build factory that copies `scorer/solution/` for the reference case.
The empty case leaves the workspace untouched.
Both cases retain the task, scorer registry, log, and results exporter.
Rubrics must stay out of free checks.

Step 2b adds agent-mode dispatch and sandbox setup in `build_task()`.
`Eval.sample()` already maps workspace files to `/workspace/` and keeps scorer files separate.
Only quiz dispatch clears the file mapping before a plain model call.
Step 2b must keep scorer files out of the agent container.

`config.yaml` holds model names, default effort, and the fixed grader selection.
Effort accepts `none`, `minimal`, `low`, `medium`, `high`, `xhigh`, or `max`.
`validate` rejects other effort values before a paid run.
`register_prices()` registers model information before use, including names absent from Inspect's database.
The search-provider setting is reserved for the internet mode and defaults to null.
