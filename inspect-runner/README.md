# Runner reference

The Python package lives in `inspect-runner/ethevals/`.
The root `pyproject.toml` installs the `ethevals` command.

## Eval folders

An eval lives at `evals/<pillar>/<name>/`.
The pillar is `concepts`, `transactions`, `building`, or `security`.
The folder contains `eval.yaml`, `workspace/`, and `scorer/scorer.yaml`.
An optional `compose.yaml` declares services for an internet epoch.
Without it, the runner uses `images/stock.compose.yaml` for quizzes and builds.
Act evals use `images/act.compose.yaml` with the shared chain service.

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
`target_scorer_spec` in `scorers.py` supplies the scorer name and arguments to the runner and HF exporter.
Both use `quiz_solver_spec` in `actors.py` for the solver.
Internet quizzes send the same formatted question through Claude Code and use the same target scorer.
For `match` and `choice`, the reference check only proves that the target matches itself.
For example, `pattern: "ERC ([0-9]+)"` and `target: "8004"` need `reference: "ERC 8004"`.

The eval hash includes file paths and bytes, including new files that the author has not committed.
Outside `scorer/`, it excludes `.DS_Store`, `out`, `cache`, `lib`, `__pycache__`, and `.pytest_cache`.
The build names `out`, `cache`, and `lib` are forbidden anywhere under `scorer/`.
Finder and Python junk remains ignored there.
The runner rejects symlinks and hard links before exclusions, including links nested inside ignored directories.
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
`--retry-errors` grants one further execution to each selected error epoch without deleting logs.
It never repeats a completed pass or failure. The next ordinary invocation still obeys the configured cap.
Player time and cost limits fail the existing checks with the limit reason. The row's `limit` field records the limit.
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
Error rows retain the fixed check names and any verdicts completed before the error.
Checks without a verdict carry `passed: false` and a `No verdict` reason. The row's verdict remains null.
Docker failures, broken reference data, and grader failures are errors on the runner's side.
A grader's explicit `passed: false` is a failed check.

## Site catalog

Run `uv run ethevals catalog --output site/.catalog` from the repository root to export public eval declarations.
The command uses the same loader and captured file manifest as execution and hashing.
`catalog.json` contains declarations, eval IDs, pillars, and hashes. It excludes scorer contents and workspace files.
The site's normal build runs this command and reads schema v3 rows. See [the site README](../site/README.md).

## Extension hooks

`SCORERS` in `scorers.py` owns each kind's schema, validation, sample fields, reference reply, and scorer factory.
Each kind also supplies its check names, workspace files, and prompt note.
The optional `setup`, `discover`, and `capture` hooks prepare services, discover names, and capture grading inputs.
Each kind supplies its cache inputs. Generic discovery stores a mapping from kind to names.
Capture hooks run before scorers. The chain closes before workspace collection.
Scorers share captured state through `Submission.captures`; the build capture owns Forge's compiled source records.
The `requires` field declares scorer order dependencies. The rubric requires tests before it.
Only `tests` supplies `foundry.toml` and the Solidity note. Internet quizzes receive neither.
A `tests` eval must omit `workspace/foundry.toml`; the loader rejects an author's copy.
A new kind returns an Inspect `Score` with `metadata["checks"]`.
Each named check requires a boolean `passed` and a nonempty `reason`.
`named_checks()` normalizes each reason to one line and passes the epoch only when all checks pass.

`CHECK_SOLVERS` in `checks.py` maps each eval type to its free-check factory.
A factory returns a `CheckRun` with a solver and a mock reply.
The build factory copies `scorer/solution/` for the reference case.
The empty case leaves the workspace untouched.
Both cases retain the task, scorer registry, log, and results exporter.
The rubric registry entry sets `free_check=False` and stays out of free checks.

Each `AGENTS` entry in `agents.py` holds one solver factory and its version. Step 3 can add factories there.
`actors.py` constructs the player and grader once, with their models, effort, and prices.
`build_task()` receives these actors. Check-only solvers and delays live in `checks.py`.
`Eval.sample()` already maps workspace files to `/workspace/` and keeps scorer files separate.
Vanilla execution clears the file mapping before a plain model call.
Internet execution sets a Docker sandbox on each sample.

`config.yaml` holds player model settings and a separate `grader` entry.
The grader entry has `model`, `effort`, `max_tokens`, `prices`, and `price_source` fields.
Effort accepts `none`, `minimal`, `low`, `medium`, `high`, `xhigh`, or `max`.
`validate` rejects other effort values before a paid run.
It also rejects harness names absent from `AGENTS`. A null harness supports vanilla mode only.
Only Opus currently declares a harness. The other configured models remain available for vanilla quizzes.
`agent_model_config` supplies the harness's model description.
Actor construction registers prices once, including names absent from Inspect's database.
Each model ID has one price schedule across both roles. Config loading rejects conflicting schedules.
`search_provider` holds the Exa MCP URL. A null value disables that MCP server.
`time_limit` supplies the fallback limit. `time_limits` sets limits by eval type.
An eval's `time_limit` takes precedence. It remains the main bound on a hung agent.
`cost_limit` gives the player $5. The grader has a computed allowance instead of a configurable minimum.
Each request caps serialized messages and generation settings at 300,000 bytes, including filenames and omission counts.
The allowance covers two calls per question, with maximum output and three serialized bytes per input token.
The estimate assumes no cache discount.
It uses the higher input or cache-write price, plus the output price.
Rows record the allowance as `grader_cost_limit_usd`. The configured two-question build allows $2.9096.
Three bytes per token is a planning estimate. Inspect enforces the allowance against reported usage.
These settings live in `config.yaml`, alongside `max_attempts: 2`.
Inspect uses the configured prices for uncached input, cache reads, cache writes, and output.
It checks cost after each call. An in-flight call can exceed its remaining budget.
The grader defaults to effort `none`, 4,096 output tokens, and a 60-second attempt timeout.
Grader calls set `max_retries=2`, so brief provider failures can recover without repeating the player epoch.
Inspect applies its backoff between attempts. Invalid replies permit at most two generation calls per question.
Player limits take precedence over scoring errors and produce a final failed row.
After a player limit, scoring skips the snapshot and grader.
`max_tasks` and `max_samples` control concurrency. Both default to four.

## Build scoring

Tests live in `scorer/tests/`. Build and act evals require `scorer/solution/`.
The runner stops the agent user's processes with SIGSTOP before collecting one snapshot into a fresh root-owned path.
It checks that those processes have stopped. PID 1 remains available to reap processes during container cleanup.
States `T`, `t`, and `Z` count as stopped. A failure to stop agent processes fails the eval's checks.
Forge and the rubric receive the same captured files. Neither scorer reads the live workspace again.
The snapshot contains only `src/` and `lib/`, excluding the runner-owned library paths before archiving.
Files outside those trees, including a `.venv`, cannot fail collection.
Nested paths such as `src/cache/` and `src/out/` remain intact.
The runner rejects archive links, unsafe paths, and special files inside the captured trees.
The archive is limited to 50 MiB of file contents and 20,000 files.
Only `.sol` files under `src/` and `lib/` enter the scorer workspace.
Submitted `lib/openzeppelin-contracts/` and `lib/forge-std/` copies never enter it.
The image supplies OpenZeppelin 5.4.0 and forge-std 1.9.7 from `/opt/ethevals/lib/`, owned by root.
The forge-std pin is `77041d2ce690e692d6e03cc812b57d1ddaa4d505`.
The runner adds the eval's tests and its own `images/foundry.toml` there.
It also supplies that configuration to the agent and states the grading rule in the prompt.
Authors can use the `@openzeppelin/contracts/` and `forge-std/` remappings.
Other dependencies require relative imports under `src/` or `lib/`. Grading ignores submitted remappings and compiler settings.
The config selects from installed compilers with `offline = true`, FFI disabled, and no filesystem permissions.
The image supplies solc 0.8.30. The prompt and compilation failures list that available compiler.
An unavailable compiler fails compilation without a download attempt. Compiler downloads happen only when the image builds.
Agent test directories and cached output do not enter the scorer workspace.
Forge runs with a clean environment, `ffi = false`, and no filesystem cheatcode permissions.
The agent and scorer have separate filesystems with no shared volumes.

Before any player epoch, the runner discovers checks with a key-free reference run in the scorer container.
It caches names under `inputs/<eval_hash>/<scoring_hash>/checks.json` and reuses them across epochs.
The scoring hash includes the eval hash, image tag, Dockerfile, Foundry config, and check-naming version.
Cache hits do not rewrite existing files.
Its test functions define `forge:<test path>:<suite>:<function signature>` checks. `forge:compile` always accompanies them.
The reference must pass. Discovery runs only for evals with missing epochs and permits one infrastructure retry.
A discovery failure enters `discovery-errors.json` and skips that eval. Other evals continue.
Discovery failures consume no player attempts. A later invocation can retry discovery.
Forge runs only tests under `test/`. Agent functions outside that expected set cannot add checks.
Compilation or submission output-limit failure fills every eval check with its reason.
A setup failure fills that suite's missing tests.
After compilation, missing expected names without a failed suite setup produce `status: error`.
Scorer-side Forge output enters log events as byte counts. Compilation reasons exclude private source lines and code frames.
Workspace failures fail all the eval's Forge and rubric checks with the snapshot reason.
The fixed set keeps the same denominator across successful and failed submissions.
Free checks omit rubric questions; paid epochs include them.

`scorer/rubric.md` has one `## stable_name` heading per question, followed by its yes-or-no question.
Each question becomes `rubric:stable_name`, independent of its position in the file.
The grader receives source contents from Forge's build info, with the agent's `src/` files first.
Imported dependencies under `lib/` follow. Unused libraries and private tests never enter the evidence.
It excludes the image's runner-owned dependencies and tells the grader where those dependencies come from.
It skips files above 100,000 bytes or beyond a 300,000-byte total, then considers smaller later files.
The request cap also counts escaped contents, filenames, and JSON structure. Files that fit retain their source-first order.
Omissions appear as `omitted_file_count`, never a list of paths.
The grader decides from the available evidence and reports uncertainty.
The runner retains that verdict even when files exceed the cap.
Files precede the question in a text block that carries Inspect's cache marker.
The runner sizes evidence against the longest question, so every question shares that evidence block.
It receives no tools and must return a boolean `passed` and a one-line `reason` in JSON.
The request uses a structured response schema. The parser requires one JSON object, with optional Markdown fences.
Prose, wrappers, or quoted objects before a verdict count as invalid replies.
Provider failures, exhausted grader budgets, and two invalid replies produce `status: error`.
Verdicts completed before a later grader error remain in the row.
An error can repeat the player epoch within the retry cap. Snapshot persistence and regrading remain deferred.
Grader calls use Inspect's `grader` role for separate token and cost accounting.
Scorer options in logs contain only the eval ID and hash. The scorer resolves captured files in process.

## Compose rules

Custom compose files use prebuilt images and declare `default` and `scorer` services.
Those two services require the stock runner image and its unprivileged `agent` user.
Other services can choose their own images. This keeps process control and runner-owned dependencies outside the eval author's control.
All services join the `private` network with `internal: true`.
Only `default` also joins the `internet` network. The scorer has no internet access.
No service publishes host ports. Privileged mode, host namespaces, host paths, and external volumes are rejected.
The agent and scorer cannot mount volumes. Other services can use declared private named volumes.
Custom Docker builds are rejected because their contexts can include scorer files.
Stock image builds use the runner-owned `images/` directory as their context.
Host environment inheritance is rejected. Service environment values must be explicit.
Decoded YAML values cannot contain `$VAR` or `${VAR}` substitutions. `$$` remains a literal dollar sign.
Only plain strings, numbers, booleans, and null are accepted as YAML scalars. Binary and timestamp values are rejected.
Compose receives the validated, re-serialized document under `inputs/<hash>/compose.yaml`, never the author's bytes.
The agent and scorer cannot override loader or shell startup environment variables.
Every privileged collector command and scorer command uses a runner-owned environment and fixed executable paths.
Author values such as `TAR_OPTIONS`, `PATH`, and `FOUNDRY_FFI` cannot alter those commands.

The normal pytest suite skips Docker proofs. Run `uv run pytest -q --run-docker -m docker` to include them.
The proofs cover Compose normalization, collection, compiled evidence, library ownership, and frozen writers.

## Act scoring

An act eval declares `scorers: [{kind: check_script}]` and `modes: [internet]`.
The [token fixture](../evals/transactions/send-six-decimal-token) sends 12.5 tokens with six decimals.
Its two checks inspect the recipient's exact balance and the transaction's sender.
Both checks fail on the untouched chain.

The stock compose file adds one `chain` service on the private network.
The chain image extends Foundry 1.5.1 at digest `sha256:3a70bfa9bd2c732a767bb60d12c8770b40e8f9b6cca28efc4b12b1be81c7f28e`.
That upstream index contains arm64 and amd64 images. Build the runner image for the host architecture first.
The chain image copies its solc 0.8.30 binary and adds Python 3 plus the filter.
Preparation builds the shared image and resolves its immutable local image ID into the execution compose file.
Rows record that SHA-256 ID. No registry push is needed.
The discovery cache includes the execution compose file, filter code, Dockerfile, and naming version.

Anvil listens at `127.0.0.1:8546` inside the chain container, with no generated accounts and no interval mining.
The filter listens at `http://chain:8545`. It accepts only JSON-RPC POST requests to `/`.
It allows standard wallet reads and `eth_sendRawTransaction`.
The full list lives in [rpc_filter.py](ethevals/images/rpc_filter.py).
It rejects the whole batch if any member names a refused method.
It rejects WebSocket upgrades, other HTTP paths, and bodies above 2 MiB.
Batches permit at most 100 requests. The filter permits at most 32 active connections.
Refused methods return JSON-RPC error `-32601`. The epoch log retains refusal messages.

The allowlist blocks unknown methods by default.
Anvil unlocks generated accounts, and `eth_sendUnsignedTransaction` bypasses signatures even without generated accounts.
Blocking only `anvil_*`, `evm_*`, and `hardhat_*` leaves those bypasses open.
Agents must sign locally with the fresh key that setup funds.

The script contract is:

- `scorer/setup.py` is optional. It runs once before the player, in `/eval` inside the chain container.
- All private files under `scorer/`, except `solution/`, reach that container from the captured eval manifest.
- Scripts run with Python 3. `RPC_URL` points directly to Anvil. `SOLC` points to `/opt/solc`.
- `cast` and `forge` are available. The chain and scorer containers have no internet access.
- Setup prints exactly one JSON object, `{"files": {"chain.json": "file contents"}}`.
- File paths must be relative workspace paths. Setup cannot replace declared workspace files.
- Only setup's selected files reach the agent. Setup can retain private state under `/eval` for the check script.
- `scorer/solution/run.sh` is required. The reference runs with Bash in the agent container after setup.
- The solution uses the same public RPC URL and key that an agent receives.
- `scorer/check.py` is required. It runs after capture, in `/eval` with direct Anvil access.
- The check script prints one JSON object keyed by stable names matching `[a-z][a-z0-9_]*`.
- Each value has exactly `passed`, a boolean, and `reason`, a nonempty string.
- The runner adds the `script:` prefix and normalizes reasons to one line.
- Setup and check scripts each have a 120-second limit and a 1 MiB output limit per stream.
- Script source and private output enter sandbox events as byte counts. Public setup values remain visible to the agent.

For example, a check script can print:

```json
{"recipient_balance": {"passed": true, "reason": "Recipient holds 12500000 base units."}}
```

A free reference run discovers names and must pass every check before player epochs can start.
The names remain fixed across passing transfers, wrong amounts, missing checks, and script crashes.
Extra runtime names cannot add checks. Missing checks fail with a reason.
A crashed, malformed, timed-out, or oversized check script fails the full set, without an error retry.
Setup failures, failed discovery, and Docker failures remain runner errors.
Player limits retain the existing final-failure rule and skip further scoring.

Capture first closes the filter under the same lock used for forwarding.
Accepted requests finish before the boundary. Further public RPC requests fail.
The runner disables mining and drops queued and pending transactions through localhost RPC.
It records the latest block hash, then stops the agent's processes before any check script runs.
The check script reads that fixed chain state. It must inspect state without changing it.
This boundary also stops detached agent senders. The agent cannot reopen the filter's local Unix control socket.

`ethevals check` runs the reference and untouched cases through this full pipeline.
The real Claude Code proof supports the act fixture with `--eval evals/transactions/send-six-decimal-token`.
`tests/prove_chain.py` exercises wrong amounts, broken checks, bypass attempts, and pending transactions.

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
