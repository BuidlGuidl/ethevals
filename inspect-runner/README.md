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
It accepts optional `choices`, a list of strings, and `addresses`, a mapping of names to strings.
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

A quiz with `choices` requires the `choice` method and letter targets, such as `C`.
The solver uses Inspect's `multiple_choice()` path without shuffled choices or chain-of-thought prompts.
Other quizzes use `generate()` without tools.

The eval hash includes every file's relative path and bytes, including workspace files and scorer files.
It excludes timestamps and permissions. Renames change the hash. Symlinks are rejected.

## Results rows

Each `rows.jsonl` file contains one flat JSON object per epoch.
The exporter replaces the file atomically after Inspect returns.
After an abrupt kill, the logs remain the recovery source until the next command exports rows.

| Fields | Meaning |
| --- | --- |
| `schema_version` | Results format version, currently `1`. |
| `eval_id`, `eval_hash`, `pillar`, `type` | Eval identity at execution time. |
| `harness`, `model`, `effort`, `mode` | Agent or bare model identity. A bare model has a null harness. |
| `grader_model`, `grader_effort`, `grader_prices_json` | Grader identity and configured prices. Free checks bind the grader to mockllm. |
| `answer_kind` | `reference`, `empty`, or `default` for mock checks. Null for paid epochs. |
| `epoch`, `status`, `passed` | Epoch number and result. Errors have a null verdict. |
| `checks_json` | JSON text keyed by check name. Each check has `passed` and a one-line `reason`. |
| `error_kind`, `error_reason` | Error details, separate from a failed check. |
| `model_tokens`, `grader_tokens`, `total_tokens` | Total token counts. Grader usage is subtracted from overall usage. |
| `token_source` | `mock` or `provider`. Mock token counts are synthetic. |
| `cost_usd`, `cost_source`, `prices_json` | Total cost, its source, and the model's configured prices. Unknown costs remain null. |
| `working_seconds`, `total_seconds` | Inspect's working time and elapsed time. Setup failures can leave these null. |
| `log_file`, `log_sample_id`, `log_epoch`, `sample_uuid` | Full log reference and Inspect's epoch identity. |

The JSON text fields keep the row flat for CSV conversion later.
Consumers must parse those strings to read their members.
The exporter reads complete logs so long reasons survive Inspect's summary truncation.
It uses `role_usage["grader"]` even when the grader and model under test share a model name.

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
It also holds the two public mode names; runner code uses their plain and agent roles.
A public rename also requires migration of eval declarations and old results.
`register_prices()` registers model information before use, including names absent from Inspect's database.
The search-provider setting is reserved for the internet mode and defaults to null.
