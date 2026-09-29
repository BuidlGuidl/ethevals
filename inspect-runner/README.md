# Runner reference

The root `pyproject.toml` installs `ethevals` from this directory.
[The root guide](../README.md) covers installation and runs.
[Add an eval](../docs/add-an-eval.md) covers author files and examples.

## Scorer kinds

The loader selects scorers from files under `scorer/`.
`SCORERS` in `scorers.py` maps each kind to an Inspect scorer factory.

| Kind | Files | Result |
| --- | --- | --- |
| Target | `target.yaml` | A quiz check through Inspect's `match`, `pattern`, or `choice`. |
| Tests | `tests/` | Build checks from Forge, including `forge:compile`. |
| Rubric | `rubric.md`, with `tests/` | One model verdict per named question after compilation succeeds. |
| Check script | `check` or `check.<ext>` | Act checks from the script's JSON output. |

Scorers run in the table's order.
Each returns check names mapped to `C` or `I` in `Score.value`.
`Score.metadata["reasons"]` holds the reasons.
The row exporter retains completed scores if a later scorer raises an error.

Target settings also drive the Hugging Face export.
`actors.quiz_solver_spec()` selects `generate` or `multiple_choice` for vanilla quizzes.
`checks.py` supplies scripted reference and empty solvers for the free check.
Build and act references overlay `scorer/solution/` on the workspace, then run optional `run.sh`.

## Captured files and build scoring

`files.py` supplies one captured manifest for hashing, workspace files, and scorer inputs.
The eval hash covers file paths and bytes, including uncommitted author files.
It excludes timestamps, permissions, and local artifacts under the manifest's exclusion rules.
The loader rejects symlinks and hard links before it applies exclusions.
Later disk edits cannot alter an already loaded eval.

Build scoring stops the agent's processes before it captures `src/` and `lib/`.
Forge and the rubric share that snapshot.
The scorer uses the image's libraries and runner-owned `foundry.toml`.
Agent tests, cached output, compiler settings, and remappings do not replace them.
The archive permits at most 50 MiB of contents and 20,000 files.
Only Solidity files enter the scorer workspace.

Forge reports `forge:<test path>:<suite>:<function signature>` checks.
Compilation failure records only `forge:compile`.
Constructor and setup failures keep the names Forge reports.
The installed compiler list comes from [solc.json](ethevals/images/solc.json).
An unavailable compiler fails compilation without a download.
Scoring disables FFI and filesystem cheatcodes, but retains network access.

Rubric evidence contains compiled source files, with agent source before imported dependencies.
It excludes private tests, unused libraries, and runner-owned libraries.
The runner serializes evidence with ASCII escapes and cuts it once at 100,000 bytes.
Every rubric question receives that same evidence block with Inspect's cache marker.
The grader has no tools and returns one JSON object with `passed` and `reason`.
Two invalid replies produce an error; an empty reason produces a failed check.

## Results rows

`rows.jsonl` contains one JSON object per epoch, using schema version 4.
The exporter writes atomically and skips unchanged content.

| Fields | Meaning |
| --- | --- |
| `schema_version` | Row format version. |
| `eval_id`, `eval_hash`, `type` | Eval identity and type. |
| `mode`, `harness`, `model`, `effort`, `epoch` | Mode, agent identity, and epoch number. |
| `attempt`, `completed_at` | Execution count and observation time. |
| `status`, `checks` | `passed`, `failed`, or `error`, with named checks and reasons. |
| `error_kind`, `error_reason`, `limit` | Error details and the Inspect limit reached. |
| `total_tokens` | Agent and grader tokens combined. |
| `model_cost_usd`, `grader_cost_usd`, `cost_source` | Role costs and their source; unknown amounts are null. |
| `working_seconds`, `total_seconds` | Inspect working and elapsed time. |
| `log_file`, `log_url` | Local log path and published URL. |

Epoch identity includes eval ID, eval hash, harness, model, effort, mode, and epoch number.
Prices, grader settings, and limits do not change that identity.
The fold selects the higher attempt, then the later completion time.
A release URL enriches the same observation without replacing a later attempt.
Logs retain config snapshots, image inputs, prices, and search events.
`role_usage["grader"]` separates grader costs even when both roles use the same model.
Search has a planning reserve but no metered row cost.

Each scheduled epoch uses one Inspect task, sample, and epoch.
Task metadata stores the ETH Evals epoch and attempt numbers.
After interruption, `plan` and `run` rebuild rows from available logs.
The runner also exports rows when Inspect raises an exception.
The Python `run()` return value covers the selection; its rows file covers the whole store.

## Limits and errors

`config.yaml` supplies working limits by eval type, cost limits, attempt counts, and concurrency.
`task_limits()` sets the wall backstop to three times the working limit.
Its scoring reserve adds Forge, script, and grader deadlines plus snapshot overhead.
Task construction rejects reserves that cannot fit Inspect's scoring window.

The grader reserve uses capped evidence, prompt, question size, and the configured output cap.
It covers two calls per question and three provider attempts per call.
`rubric_budget()` uses the largest configured input price without a cache discount.
Each grader call has a total deadline that includes provider retry backoff.
The constants live beside the scorer implementation.

| Event | Row result |
| --- | --- |
| Incorrect answer, failed test, or negative rubric verdict | Failed check. |
| Agent working or cost limit | Failed check; further scoring work stops. |
| Invalid submission or unsafe captured archive | Failed `forge:compile` check. |
| Operator stop or wall stop before the working limit | Error. |
| Docker failure, memory failure, or setup failure | Error. |
| Grader provider failure or exhausted grader allowance | Error with any completed scorer results. |
| Script crash or malformed verdict | Error. |
| Scoring exec timeout | Failed check. |
| Forge output without results or a compiler diagnostic | Error. |

Inspect retains the last 10 MiB of each exec stream.
Truncated script output can become malformed JSON; truncated Forge output can lack required results.
A Compose preparation failure records `preparation-errors.json` without consuming an epoch attempt.
A stock image-build failure stops the run with Docker's diagnostic.

`--wall-seconds` reserves preparation once, then admits shortest epochs while their summed bounds fit.
Each bound includes the task's wall and scoring limits, plus container time for sandbox modes.
Deferred epochs remain missing for a later run.
A single epoch that cannot fit an empty window produces a config error.
These estimates do not enforce a separate preparation deadline.

## Compose and agents

An eval's optional `compose.yaml` declares extra services and named volumes.
The runner owns `default`, `scorer`, `chain`, and the networks.
Every extra service needs an image and a positive `mem_limit`; it joins only `private`.
Authors must pin extra-service images by digest; the runner does not enforce that rule.
The merged memory limits at configured concurrency must leave 1 GiB for the host.

Validation rejects privileged mode, host mounts, host namespaces, custom builds, and external volumes.
It also rejects inherited host environment values and host-variable interpolation.
The runner serializes the merged document to `inputs/<hash>/compose.yaml`.
Stock image tags come from [images/tag.py](ethevals/images/tag.py), independent of eval hashes.
Tags identify build inputs, not reproducible image bytes.

The agent, scorer, and chain have internet access.
Anvil's unfiltered RPC listens only on loopback inside the chain container.
The agent uses the filter at `http://chain:8545`.
[rpc_filter.py](ethevals/images/rpc_filter.py) lists allowed wallet reads and signed transaction calls.
A batch with any refused method fails as a whole.
The filter rejects WebSockets and unsigned sends; refusal messages enter the Inspect log.

`agents.py` defines harness factories and pins their versions.
`actors.py` pairs a harness with the configured model, effort, and prices.
`agent_model_config` selects the CLI's model identity.
Model requests pass through Inspect's host bridge.
Exa search also runs on the host, which alone reads optional `EXA_API_KEY`.
`search_limit` caps search and fetch calls together; failed calls consume a slot.
Per-call caps and hosted tool schemas live in `search.py` and `exa-tools.json`.

## Script contract

Setup and check scripts are runnable files under `scorer/`; their shebangs select installed interpreters.
Their names are `setup` or `setup.<ext>`, and `check` or `check.<ext>`.
They run in `/eval` inside the chain container with internet access.
`cast`, `forge`, and `jq` are available.

| Variable | Value |
| --- | --- |
| `RPC_URL` | Private, unfiltered chain RPC. |
| `PUBLIC_RPC_URL` | The agent's filtered RPC. |
| `SOLC` | Installed compiler path. |

Setup prints `{"files": {"chain.json": "file contents"}}`.
Paths must be relative and cannot replace declared workspace files.
Only these selected files reach the agent; other setup state stays in `/eval`.
Setup runs before the agent's time allowance starts.

Check output maps names matching `[a-z][a-z0-9_]*` to boolean `passed` and nonempty string `reason` values.
For example:

```json
{"balance": {"passed": true, "reason": "Recipient has the required balance."}}
```

The runner prefixes names with `script:` and normalizes reasons to one line.
Scripts must report verdicts for failed agent work, rather than crash.
Both scripts have a 120-second timeout; failures include the last 4 KiB of stderr.
Before checking chain state, the runner stops agent processes and awaits a manual mine.
The checker can send further transactions while automining remains active.

## CI and publication

[checks.yml](../.github/workflows/checks.yml) runs free checks on pull requests without provider secrets.
[results.yml](../.github/workflows/results.yml) queues paid runs after main changes, excluding results-only changes.
It uses `OPENROUTER_API_KEY`, optional `EXA_API_KEY`, and the `ETHEVALS_BUDGET_USD` repository variable.
A manual dispatch budget overrides that variable; the fallback budget is zero.
The paid job has no write token. A separate publisher always runs afterward.

`scripts/ci.py after-merge` restores pending results and calls the main runner CLI.
`publish-results` rebuilds each artifact's rows and records them before any log upload.
It folds `origin/main`, `origin/ci/results`, and artifact rows onto current main.
Successful uploads add log links and update the results pull request without a force push.
A retry can reopen a missing pull request without repeating a successful push.
If publication fails, rerun the workflow before starting another paid run to avoid paying for missing rows again.
Exhausted error epochs remain visible in the plan; a completed no-op succeeds.

`ethevals publish-logs --output DIR --repo OWNER/REPO --run-id ID --commit SHA` previews a log release.
Adding `--publish` uploads through `gh` and writes `DIR/published/results-ID.jsonl` after success.
It skips linked logs and non-final errors. The preview writes nothing.
CI gets the release's source commit from its Inspect logs.

`ethevals export-hf --output DIR` writes vanilla quizzes to an empty directory.
`--hf-repo` and `--license` set dataset card values.
`scripts/ci.py release` previews the HF upload; `--publish` performs it.

## Maintainer checks

Run `uv run pytest -q` for unit tests.
Run `uv run pytest -q --run-docker -m docker` for the container proofs.
Tests use the config factories in `tests/conftest.py`.
`--run-live-exa -m live_exa` opts into hosted Exa schema checks.

The agent proof also remains a command:

```sh
uv run python inspect-runner/tests/prove_agent.py reference --exa-canary --output /tmp/agent-reference
uv run python inspect-runner/tests/prove_agent.py empty --exa-canary --output /tmp/agent-empty
```

Strip provider credentials before these commands.
`--exa-canary` uses offline search replies and checks that its inert key stays out of containers and logs.
