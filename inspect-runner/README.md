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
| Check script | `check` or `check.<ext>` | Act checks from the script's JSON output. |
| Rubric | `rubric.md` | One model verdict per named question, after the eval's other scorer. |

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

Build rubric evidence contains compiled source files, with agent source before imported dependencies.
It excludes private tests, unused libraries, and runner-owned libraries.
Other evals use non-system message roles and text, with tool-call IDs, functions, arguments, results, and errors.
Transcript evidence drops reasoning, signatures, metadata, and tool views.
Evidence uses JSON with ASCII escapes and a 100,000-byte cap.
Builds keep the prefix; transcripts keep the suffix to preserve the final reply and recent tool results.
The cut can leave partial JSON or omit earlier calls. The grader must state uncertainty when evidence is incomplete.
Every rubric question receives that same evidence block.
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
Row costs cover model tokens only. Providers bill search separately.

Each scheduled epoch uses one Inspect task, sample, and epoch.
Task metadata stores the ETH Evals epoch and attempt numbers.
After interruption, `plan` and `run` rebuild rows from available logs.
The runner also exports rows when Inspect raises an exception.
The Python `run()` return value covers the selection; its rows file covers the whole store.

## Limits and errors

`config.yaml` supplies working limits by eval type, cost limits, attempt counts, and concurrency.
`task_limits()` sets the total limit to the larger of three working limits or two scoring reserves.
Its scoring reserve adds Forge, script, and grader deadlines plus snapshot overhead.
After the solver stops, Inspect gives scoring its own window of half the total limit.

The grader reserve uses capped evidence, prompt, question size, and the configured output cap.
It covers two calls per question and three provider attempts per call.
`rubric_budget()` uses the largest configured input price without a cache discount.
The direct Anthropic grader uses low effort and `max_tokens: 32768`, which includes thinking and the JSON verdict.
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

Plans reserve a budget for every missing epoch.

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
[rpc_methods.json](ethevals/images/rpc_methods.json) classifies every RPC name and alias in pinned Anvil as `allow` or `deny`.
[rpc_filter.py](ethevals/images/rpc_filter.py) reads its allow list from that file and refuses every other method.
It allows wallet reads, polling filters, access lists, block receipts, simulations, and signed transaction calls.
It refuses `debug_*`, `trace_*`, `ots_*`, `txpool_*`, chain controls, and node signing.
Node-signing refusals say: "Sign locally and use eth_sendRawTransaction."
A batch with any refused method fails as a whole.
The filter rejects WebSockets and unsigned sends; refusal messages enter the Inspect log.
The network guard in `tests/test_rpc_methods.py` fetches Foundry source at the tag in `images/Chain.Dockerfile`.
It fails on missing or stale classifications and runs with `uv run pytest -q` in the free PR check.

`agents.py` defines harness factories and pins their versions.
`config.yaml` lists `models` with provider slugs and optional effort, and `agents` with harnesses and model keys.
Each agent's `cli_model` selects its CLI's model identity. Agents inherit effort from their model entry.
Each agent declares `search: native` or `search: exa`.
Native search requires Claude Code with an `anthropic/` model or Codex CLI with an `openai/` model.
`actors.py` sets Inspect's `reasoning_effort` from that entry; `--effort low|medium|high|xhigh` overrides it for a run.
Omitted effort leaves the provider's default in effect and records `effort: null` in rows.
`--models` selects vanilla models; `--agents` selects internet and skills agents.
Without `--modes`, one selector selects its matching modes. Both or neither select all modes.
An omitted selector includes all entries of its kind in the selected modes.
Model requests pass through Inspect's host bridge.
Claude Code and Codex use their providers' own search.
Claude Code sets `CLAUDE_CODE_MAX_WEB_SEARCHES_PER_SESSION` to `search_limit`; each call allows up to eight searches.
Codex uses live search. Its search count is not capped.
Setting `search: false` at the config root disables search for every agent.
Exa search also runs on the host, which alone reads optional `EXA_API_KEY`.
For Exa, `search_limit` caps search and fetch calls together; failed calls consume a slot.
Per-call caps and hosted tool schemas live in `search.py` and `exa-tools.json`.

## Plan and run

Check model names, effort settings, and prices in [config.yaml](ethevals/config.yaml).
The checked-in prices are guesses.
Use `--config path/to/config.yaml` for a separate configuration.
[ADR 0006](../docs/adr/0006-direct-provider-keys-and-native-search.md) records the provider and search decisions.

Print missing work without keys, Docker, or model calls:

```sh
uv run ethevals plan --models opus-5.5 --agents claude-code-opus-5.5 --modes vanilla internet --epochs 1 --budget 100
```

`--budget` is a USD ceiling for the plan's agent and grader reserve, including remaining error attempts.
A plan that exceeds the budget exits with code 1.
The runner rejects that plan before it constructs providers or prepares containers.
Cost limits use configured prices and check usage after calls.
An in-flight call can exceed the remaining allowance.
The budget reserve is not a provider billing cap.

Paid runs require keys for each selected provider and the grader.
Opus and the grader use `ANTHROPIC_API_KEY`. GPT uses `OPENAI_API_KEY`.
Kimi and GLM use `OPENROUTER_API_KEY`.
The runner reports all missing keys before constructing providers or starting containers. Keys stay on the host.
For the first paid command, see [the root guide](../README.md#run-with-provider-keys).
For Codex, also set `OPENAI_API_KEY` and replace the agent with `codex-cli-gpt-5.5`.
Only a paid run proves provider access, usable search results, and grader output.

Use `--evals` to select folders and `--output` to choose a results directory.
An explicit `--modes` must match each selector.
Each eval runs only in modes it declares.
The skills mode adds the repo's Ethereum skills pack to the internet mode.

`run` succeeds when execution succeeds, even when an agent fails its checks.
Repeat the command to resume missing epochs.
A log that can't be read, such as one cut off by a killed run, is skipped with a warning, and its epoch runs again.
Completed passes and failures remain final.
Errors can run again within `max_attempts`; `--retry-errors` grants one further execution per selected error epoch.
The runner reads committed results from `results/rows.jsonl` by default.
Use `--rows` to select a different resume file.
The full transcript stays in the Inspect log.
To browse a local run, use `uv run inspect view --log-dir results/logs`.

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
[results.yml](../.github/workflows/results.yml) queues paid runs after `main` changes, excluding results-only changes.
It uses `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `OPENROUTER_API_KEY`, optional `EXA_API_KEY`, and the `ETHEVALS_BUDGET_USD` repository variable.
A manual dispatch budget overrides that variable; the fallback budget is zero.
The paid job has no write token and a six-hour limit.
Its run step stops after 340 minutes, which leaves time to upload finished epochs even after a timeout.
A separate publisher holds no model keys and runs after failed or timed-out steps on `main`.
It downloads artifacts from every attempt of the workflow run. The next run resumes missing epochs.

`scripts/ci.py after-merge` restores pending results and calls the main runner CLI.
`publish-results` rebuilds each artifact's rows and records them before any log upload.
It folds `origin/main`, `origin/ci/results`, and artifact rows onto current `main`.
Successful uploads add log links and update the results pull request without a force push.
A retry can reopen a missing pull request without repeating a successful push.
If publication fails, rerun the workflow before starting another paid run to avoid paying for missing rows again.
Exhausted error epochs remain visible in the plan; a completed no-op succeeds.

`ethevals publish-logs --output DIR --repo OWNER/REPO --run-id ID --commit SHA` previews a log release.
Adding `--publish` uploads through `gh` and writes `DIR/published/results-ID.jsonl` after success.
It skips linked logs and non-final errors. The preview writes nothing.
CI gets the release's source commit from its Inspect logs.

`ethevals export-hf --output DIR` writes vanilla quizzes to an empty directory.
It skips quizzes with rubrics and prints the reason.
`--hf-repo` and `--license` set dataset card values.
`scripts/ci.py release` previews the HF upload; `--publish` performs it.
[release.yml](../.github/workflows/release.yml) publishes to `buidlguidl/ethevals-test` on every push to `main` with `HF_TOKEN`.
It tags dataset changes `gh-<short sha>` and supports manual reruns without inputs.

## Maintainer checks

Run `uv run pytest -q` for unit tests.
Run `uv run pytest -q --run-docker -m docker --ignore=inspect-runner/tests/test_agents_docker.py` for the CI container checks.
Tests use the config factories in `tests/support.py`.

The real CLI proofs run separately:

```sh
uv run python inspect-runner/tests/prove_agent.py reference --agent claude-code-opus-5.5 --eval evals/concepts/agent-registries --output /tmp/claude-reference
uv run python inspect-runner/tests/prove_agent.py reference --agent codex-cli-gpt-5.5 --eval evals/concepts/agent-registries --output /tmp/codex-reference
```

Strip provider credentials before these commands.
Claude Code and Codex proofs require native search through mockllm and check the CLI's next request.
OpenCode proofs use Exa.
`--exa-canary` selects Exa with offline replies and checks that its inert key stays out of containers and logs.
