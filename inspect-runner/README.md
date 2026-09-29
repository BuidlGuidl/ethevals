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
The internet mode supports Claude Code, Codex CLI, and OpenCode. The skills mode is not implemented.
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
Internet quizzes send the same formatted question through the selected agent and use the same target scorer.
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
The exporter folds new rows into the existing file and replaces it atomically after Inspect returns.
It skips the write when the content is unchanged.
`--rows results/rows.jsonl` adds committed rows to the resume record without requiring their logs.
CI uses a fresh output directory and reads only that run's logs.
After an abrupt kill, the logs remain the recovery source until the next command exports rows.
The runner also exports rows if `eval()` raises. Both `plan` and `run` fold rows from these logs.
CI rebuilds rows from each run's logs and commits them before log uploads.
The publisher folds those rows with `origin/main` and `origin/ci/results`.
It builds the results commit on current `origin/main`, even when its checkout is older.
See the root README for workflow setup.
The log store only grows. Retry logs never replace earlier logs.
Rows cover the whole store, with the latest row per eval ID, eval hash, agent, mode, and epoch number.
The fold chooses the higher attempt count, then `completed_at`. A release link enriches the same observation.
The agent consists of harness, model, and effort. Vanilla epochs have a null harness.
Mock answer kinds also distinguish identities so reference and empty answers cannot share results.
Prices, grader settings, and execution limits do not change an existing epoch's identity.
Their recorded values describe the execution that produced the row.
Changing a limit applies to missing epochs. A completed limit failure remains final.

Each scheduled epoch has one Inspect task with one sample and one Inspect epoch.
Task metadata holds the ETH Evals epoch number. `log_epoch` holds Inspect's epoch number.
This lets the runner select missing epochs without using Inspect's broader task identity.
`max_attempts` permits two executions per identity, including errors and interrupted executions recorded in logs.
After the second error, the plan lists the exhausted epoch without another model call.
`--retry-errors` grants one further execution to each selected error epoch without deleting logs.
It never repeats a completed pass or failure. The next ordinary invocation still obeys the configured cap.
Player working-time and cost limits fail the existing checks with the limit reason. The row's `limit` field records the limit.
Operator stops and wall-clock stops before the working limit produce errors.
`check` writes fresh logs on every invocation and checks only the current selection.
The Python `run()` result also contains only the current selection. `rows.jsonl` contains the whole store.

`ethevals plan --rows results/rows.jsonl --modes vanilla internet` prints missing epochs without keys, Docker, or model calls.
It shares epoch selection with `run` and uses the runtime's `cost_limit`, `rubric_budget`, and `max_attempts`.
`run()` owns the paid gate. A paid run requires `--budget` before provider construction.
Search adds `search_limit * search_price_usd` to each internet attempt's reserve.
`plan --budget USD` exits with code 1 when the worst-case cost exceeds the budget.
The plan also lists exhausted errors.
See the root README for the limits of this cost estimate.

| Fields | Meaning |
| --- | --- |
| `schema_version` | Results format version, currently `3`. |
| `eval_id`, `eval_hash`, `pillar`, `type` | Eval identity at execution time. |
| `harness`, `model`, `effort`, `mode` | Agent or bare model identity. A bare model has a null harness. |
| `harness_version`, `images` | Harness version and service image tags used for this execution. |
| `runner_inputs`, `chain_inputs` | SHA-256 hashes of each stock image's Dockerfile and copied files. Both include `solc.json`. |
| `grader_model`, `grader_effort`, `grader_prices` | Grader identity and configured prices. Free checks bind the grader to mockllm. |
| `answer_kind` | `reference`, `empty`, or `default` for mock checks. Null for paid epochs. |
| `epoch`, `status`, `passed` | Epoch number and result. Errors have a null verdict. |
| `attempt`, `max_attempts` | Execution count and configured cap per identity. |
| `model_metered_usd`, `grader_metered_usd` | Dollars recorded by Inspect's cost meter for each role. Mock usage can have synthetic prices. |
| `cost_limit_usd`, `grader_cost_limit_usd`, `limit` | Separate budgets and any player limit that stopped execution. |
| `working_limit_seconds`, `time_limit_seconds`, `scoring_limit_seconds` | Player working limit, wall-clock backstop, and total scoring deadline. |
| `search_calls`, `search_failed`, `search_rate_limited`, `search_capped` | Search and fetch calls, failed results, Exa throttling, and our cap refusals. Repeated model inputs count once. |
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
Sandbox initialization runs setup hooks before Inspect starts the player's limits and working-time clock.
The generic boundary stops the agent once, then calls each selected capture hook before scoring.
Scorers share captured state through `Submission.captures`; the build capture owns Forge's compiled source records.
`scoring_base.py` owns the shared types and `SubmissionFailed`. The generic scorer catches that exception once to fail the fixed set.
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

Each `AGENTS` entry in `agents.py` holds one solver factory and its version.
`Harness.build()` supplies the version and host-side Exa tool bridge to that factory.
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
All four configured models declare a harness and remain available for vanilla quizzes.
`agent_model_config` supplies the CLI model identity.
Actor construction registers prices once, including names absent from Inspect's database.
Each model ID has one price schedule across both roles. Config loading rejects conflicting schedules.
`search_provider` accepts `https://mcp.exa.ai/mcp` or null. Null disables search.
The host sends optional `EXA_API_KEY` in an HTTP header. The bridge exposes no key to any harness.
Keyed and keyless requests use the same host-side path. Logs and agent configuration contain no key.
`search_limit` caps search and fetch requests together at 20 per epoch. Failed requests consume a slot.
The bridge keeps hosted schemas in `exa-tools.json` and adds its per-call limits to each tool description.
Search clamps `numResults` to 1–10 whole results, default 10. Fetch rejects batches above 5 URLs.
The optional `--run-live-exa -m live_exa` test compares the raw hosted snapshot. Free CI checks never call Exa.
The host logs HTTP status and JSON-RPC error code and message, with the key redacted.
Keyed search remains unverified until the first keyed run.
The plan reserves the configured `search_price_usd`, currently a guessed $0.05, for every slot, including keyless runs.
Check this price before funding a run. Rows retain the limit, price, and search outcome counts.
The reserve covers the per-call caps and totals $1 per internet attempt.
`time_limit` supplies the fallback working-time limit. `time_limits` sets working limits by eval type.
An eval's `time_limit` takes precedence.
Quizzes allow 300 working seconds; builds and acts allow 1,200. Inspect excludes retry backoff and sandbox waits.
The wall-clock backstop is three times the working limit: 900 seconds for quizzes and 3,600 seconds for builds and acts.
`cost_limit` gives the player $5. The grader has a computed allowance instead of a configurable minimum.
Each request caps serialized messages and generation settings at 300,000 bytes, including filenames and omission counts.
Evidence uses ASCII escapes. The allowance reserves one input token per serialized byte.
It covers two calls per question and three provider attempts per call, including abandoned attempts absent from reported usage.
The formula is `questions * 2 * (max_retries + 1) * (300000 * max(input, cache_read, cache_write) + max_tokens * output) / 1000000`.
`rubric_budget(evaluation, config)` supplies this ceiling for rows and the CI budget gate.
Rows record it as `grader_cost_limit_usd`. The configured two-question build reserves $23.7288.
The ceiling assumes the configured prices and output cap. It grants no cache discount.
These settings live in `config.yaml`, alongside `max_attempts: 2`.
Inspect uses the configured prices for uncached input, cache reads, cache writes, and output.
It checks cost after each call. An in-flight call can exceed its remaining budget.
The grader defaults to effort `none` and 4,096 output tokens.
Each generation call has a 60-second total deadline, including backoff, and a 20-second attempt timeout.
Grader calls set `max_retries=2`, so brief provider failures can recover without repeating the player epoch.
Inspect applies its backoff between attempts. Invalid replies permit at most two generation calls per question.
Two questions permit 240 seconds of grader calls plus 180 seconds of Forge execution.
The total scoring deadline adds 120 seconds for snapshot and transfer work, for 540 seconds in the current build.
Act scoring allows 120 seconds for the check script plus 120 seconds for capture and transfer, for 240 seconds total.
Task creation requires that deadline to fit inside Inspect's scoring window, half the wall-clock backstop.
Player working-time and cost limits take precedence over scoring errors and produce a final failed row.
After a player limit, scoring skips the snapshot and grader.
An operator stop or a wall-clock stop before the working limit produces an error row.
`max_tasks` and `max_samples` control concurrency. The checked-in config sets both to one.

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
The scoring hash includes the eval hash, service image names, computed stock image names, grading config, and check-naming versions.
An edit to `foundry.toml` invalidates discovered checks without renaming either image.
Cache hits do not rewrite existing files.
Its test functions define `forge:<test path>:<suite>:<function signature>` checks. `forge:compile` always accompanies them.
The reference must pass. Discovery runs only for evals with missing epochs and permits one infrastructure retry.
A discovery failure appends to `discovery-errors.json` and skips that eval. Other evals continue.
The error names failed tests, their reasons, and the compiler diagnostic when present.
Discovery failures consume no player attempts. A later invocation can retry discovery.
Forge runs only tests under `test/`. Agent functions outside that expected set cannot add checks.
Compilation or submission output-limit failure fills every eval check with its reason.
A failed `constructor()` or `setUp()` fills that suite's missing tests.
After compilation, unexplained missing names produce `status: error`.
Unknown signal exits and output without results or a compiler diagnostic also produce errors.
Invalid Solidity bytes and confirmed OOM kills fail the fixed checks.
Stock limits are 3 GiB for the agent, 2 GiB for the scorer, and 256 MiB for the chain.
Each extra service declares its own memory limit. Capacity sums the merged Compose limits.
The capacity check reserves another 1 GiB for the host before preparation.
Scoring reads `memory.events` before each command and after OOM-like failures, including Forge's killed compiler child.
Both `oom` and `oom_kill` must rise for that command. Ordinary failed tests need no second memory exec.
A host kill without both deltas remains an error. An agent CLI exit 137 with both deltas fails every check.
Other CLI failures remain errors. Rows record the agent container's `memory.peak` in `agent_memory_peak_bytes`.
Task notes tell the agent its memory limit. Setup uses the runner executor, not the scoring executor.
Docker exec failures and capture timeouts remain errors. Only a known submission-rule violation raises `SubmissionFailed`.
Forge streams through readers with a 10 MiB cap per stream and one extra byte to detect overflow.
The wrapper waits for both reader process IDs before the scorer reads each file.
The cap applies only to captured output, so Forge can write larger build-info files.
Compilation reasons use the coded diagnostic. Only compiler-version failures list available compiler versions.
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
A schema-valid reply with an empty reason fails that rubric check with a runner-supplied reason.
Verdicts completed before a later grader error remain in the row.
An error can repeat the player epoch within the retry cap. Snapshot persistence and regrading remain deferred.
Grader calls use Inspect's `grader` role for separate token and cost accounting.
Scorer options in logs contain only the eval ID and hash. The scorer resolves captured files in process.

## Compose rules

An eval's optional `compose.yaml` lists extra services and named volumes only.
The runner supplies `default`, `scorer`, `chain`, and the networks, then writes the computed stock image tags.
Each extra service needs an image and a positive `mem_limit`. It joins only `private`, which the runner supplies by default.
The merged limits plus a 1 GiB host reserve must fit Docker memory at the configured concurrency.
There is no service-count cap.
The agent, scorer, and chain containers also join `internet`. Author services cannot join it.
Anvil's unfiltered RPC listens on loopback inside the chain container, beyond the agent's reach.
CI rejects privileged mode, host mounts, host namespaces, external volumes, custom builds, and host environment inheritance.
Explicit environment values cannot interpolate host variables. Named volumes are allowed for extra services.
The runner validates and serializes the merged file under `inputs/<hash>/compose.yaml`.
Stock image builds use the runner-owned `images/` directory. Stock files contain no image tags.
Every scorer command uses a runner-owned environment.

The normal pytest suite skips Docker proofs. Run `uv run pytest -q --run-docker -m docker` to include them.
The proofs cover Compose normalization, collection, compiled evidence, library ownership, and frozen writers.
They also run reference and untouched-workspace scripts through each of the four configured agents.
Each agent proof makes one real Exa search and records the raw CLI effort in `cli-requests.jsonl`.
OpenCode proofs check the selected system prompt and model identity.

## Act scoring

An act eval declares `scorers: [{kind: check_script}]` and `modes: [internet]`.
The [token fixture](../evals/transactions/send-six-decimal-token) sends 12.5 tokens with six decimals.
Its two checks inspect the recipient's exact balance and the transaction's sender.
Both checks fail on the untouched chain.

The stock compose file adds one `chain` service on the private and internet networks.
The chain image builds independently and includes jq for shell scripts.
It copies Foundry 1.5.1 binaries from digest `sha256:3a70bfa9bd2c732a767bb60d12c8770b40e8f9b6cca28efc4b12b1be81c7f28e`.
Its Python 3.13.7 base uses digest `sha256:adafcc17694d715c905b4c7bebd96907a1fd5cf183395f0ebc4d3428bd22d92d`.
Both image indexes include arm64 and amd64.
Both images read the compiler version, URLs, and per-architecture SHA-256 checksums from [solc.json](ethevals/images/solc.json).
The amd64 compiler comes from ethereum/solc-bin. The arm64 compiler comes from nikitastupin/solc, which Foundry also uses.
Preparation builds both images and retains their computed names in the execution compose file.
Rows record both names in `images`, with file hashes in `runner_inputs` and `chain_inputs`. No registry push is needed.
Additional custom services have no stock input hashes. An absent chain has an empty `chain_inputs` mapping.
A build failure becomes that eval's discovery error and includes Docker's last 8 KiB of diagnostics.
The discovery cache includes both image names, the eval hash, grading config, and naming versions.

Anvil listens at `127.0.0.1:8546` inside the chain container, with no generated accounts and no interval mining.
The filter listens at `http://chain:8545`. It accepts only JSON-RPC POST requests to `/`.
It allows standard wallet reads and `eth_sendRawTransaction`.
The full list lives in [rpc_filter.py](ethevals/images/rpc_filter.py).
It rejects the whole batch if any member names a refused method.
It rejects WebSocket upgrades, other HTTP paths, and bodies above 2 MiB.
Batches permit at most 100 requests.
Refused methods return JSON-RPC error `-32601`. The epoch log retains refusal messages.
Capture includes the refusal log in an Inspect info event.
Upstream responses above 2 MiB return `Chain response too large.`

The allowlist blocks unknown methods by default.
Anvil unlocks generated accounts, and `eth_sendUnsignedTransaction` bypasses signatures even without generated accounts.
Blocking only `anvil_*`, `evm_*`, and `hardhat_*` leaves those bypasses open.
Agents must sign locally with the fresh key that setup funds.

The script contract is:

- Each script is one runnable file named `check` or `check.<ext>`, or optional `setup` or `setup.<ext>`, under `scorer/`.
- The runner executes the file itself. Its shebang selects Bash, Python, or another installed interpreter.
- Scripts run in `/eval` inside the chain container with internet access. `cast`, `forge`, and `jq` are available.
- `RPC_URL` points to unfiltered Anvil, `PUBLIC_RPC_URL` points to the agent's filtered RPC, and `SOLC` names the installed compiler.
- Setup prints `{"files": {"chain.json": "file contents"}}`. Paths must be relative and cannot replace declared workspace files.
- Only selected output files reach the agent. Private setup state stays in `/eval` for the check script.
- Reference files under `scorer/solution/` overlay the workspace, then an optional `run.sh` runs. Build and act evals share this rule.
- Check output maps names matching `[a-z][a-z0-9_]*` to boolean `passed` and nonempty string `reason` values.
- The runner adds the `script:` prefix and normalizes reasons to one line.
- Setup and check each have a 120-second timeout. Setup finishes before the agent's clock starts.
- Script crashes and malformed output are errors. The free check rejects an error in either the reference or untouched run.

For example, a check script can print:

```json
{"recipient_balance": {"passed": true, "reason": "Recipient holds 12500000 base units."}}
```

A free reference run discovers names and must pass every check before player epochs can start.
The names remain fixed across passing transfers, wrong amounts, missing checks, and script crashes.
Extra runtime names cannot add checks. Missing checks fail with a reason.
A crashed or malformed author check script is an error.
An agent CLI exit 137 caused by its own container OOM is the second deliberate fail-closed rule.
The wrapper clears the old author status before each script. Missing status, reader failures, and FIFO failures remain errors.
Scripts must return a verdict for any chain state. A checker crash records an error.
An in-container timeout or output overflow also fails the full set.
Missing scripts, wrapper exit 125, host exec timeouts, and output-copy failures remain errors.
Setup failures, failed discovery, and Docker failures remain runner errors.
Player working-time and cost limits fail the fixed set and skip further scoring.
Operator stops and wall-clock stops before the working limit remain errors.
The [classification table](../README.md#failure-classification) lists every boundary.

The generic boundary first stops the agent's processes, including detached senders.
The runner waits for a manual mine because Anvil can return before mining finishes.
The unfiltered RPC stays private during grading.

`ethevals check` runs the reference and untouched cases through this full pipeline.
The real Claude Code proof supports the act fixture with `--eval evals/transactions/send-six-decimal-token`.
`tests/prove_chain.py` exercises wrong amounts, broken checks, bypass attempts, and pending transactions.

The agent registry includes Claude Code, Codex CLI, and OpenCode, with pinned versions beside their factories.
Kimi and GLM use the same OpenCode factory. The player supplies the real model and effort to Inspect.
OpenCode receives `openrouter/moonshotai/kimi-k3` or `openrouter/z-ai/glm-5.3` from configuration.
It selects the Kimi prompt for Kimi and the default prompt for GLM.
`images/opencode-models.json` declares their provider metadata, including context and output limits.
The limits use OpenRouter's `top_provider` values checked September 28, 2026.
See the [agent configuration and sources](../README.md#run-with-openrouter).
The factory supplies a dummy OpenRouter credential inside the container. The bridge selects the host-side model.

Claude Code gets `CLAUDE_CODE_EFFORT_LEVEL`; Codex gets `model_reasoning_effort`.
OpenCode gets the model option `reasoning.effort`. All receive the configured effort value, currently `high`.
Inspect separately applies the backend effort after dropping CLI generation settings.
The proof records requests before that conversion, without setting effort on its mock model.

Inspect 0.3.271 forwards namespaced custom tools to non-OpenAI providers but does not restore the reply type.
`CodexModel` wraps the active player and converts well-formed replies.
Every requested model name resolves through the bridge's fallback to that active player.
The bridge still owns generation and delivers events to inspect_swe's `CodexConsumer`.
Malformed replies remain function calls for Codex to reject. A regression test detects when Inspect fixes the conversion.
All factories explicitly set `retry_refusals=0`.

All agents get host-side `web_search_exa` and `web_fetch_exa` through Inspect's MCP bridge.
`search_rate_limited` counts Exa throttling. `search_capped` counts refusals from our shared per-epoch cap.
Agent proofs require a structured result with a title, URL, and content field.
Claude Code disables `WebSearch`; Codex disables `web_search` to avoid provider-hosted search APIs.
OpenCode's OpenRouter provider does not register `websearch` by default.
Its built-in search calls the same keyless Exa endpoint when enabled through optional search flags.
Claude Code keeps `WebFetch`, and OpenCode keeps `webfetch`. Codex has no native page-fetch tool.
Every agent keeps a shell with network access.
The stock image includes Node 20.11.0 and ripgrep for OpenCode.
Both image names hash their Dockerfile and copied files, in the order declared by `images/tag.py`.
Each filename and file's bytes have a NUL separator. The name uses the first 16 hexadecimal characters of SHA-256.
The runner's inputs are `Dockerfile` and `solc.json`. The chain adds `rpc_filter.py` to `Chain.Dockerfile` and `solc.json`.
Grading settings in `foundry.toml` affect the check cache only.
Names identify inputs, not image bytes. The runner's apt packages remain unpinned, so fresh builds can differ.
The bridge downloads and stages the pinned agent binaries at runtime.

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
Publication skips non-final error rows as well as key-free, stale-hash, and skills rows.
It skips hidden rows and logs already linked to releases. Keep publication files when reusing a results folder.
Each command accepts only its own flags. Export, proof, and publish commands require explicit output paths.
`validate` rejects alternative targets and extra scorers on vanilla quizzes.
