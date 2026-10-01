# Runner reference

The root `pyproject.toml` installs `ethevals` from this directory.
[The root guide](../README.md) covers installation and runs.
[Add an eval](../docs/add-an-eval.md) covers author files and examples.

## Eval folders

`eval.yaml` declares `prompt`, `motivation`, `modes`, and optional `choices` and `chain`.
The loader rejects unknown keys.
`chain` accepts `anvil` or a pinned fork; omission means no chain.

`scorer/` is required. `workspace/`, `setup/`, and top-level `solution/` are optional.
Tests or a chain require `solution/`.
A chain requires `setup/setup.s.sol`, and `setup/` requires a chain.
Vanilla requires no chain, no workspace files, and no tests.

Validation rejects duplicate check names across targets, test functions, and rubric headings.
The name `compile` is reserved, and `testFail*` functions are forbidden.
The prompt and workspace text reject whole words, without regard to case:
`epoch`, `grader`, `rubric`, `score`, `benchmark`, `eval`, and `being tested`, including plurals.

## Scorer kinds

The loader selects scorers from files under `scorer/`.
`SCORERS` in `scorers.py` maps each kind to an Inspect scorer factory.
The tests scorer picks test tools from file names in `scorer/tests/`, through the `RUNNERS` table in `scorers.py`.
Its one entry is Forge, which claims `*.t.sol`.
Each runner declares its file pattern, name parser, preparation, command, timeout, fork timeout, result parser, and optional source evidence.
Validation and scoring use the same runner patterns.
Files no runner claims are helpers. A tests folder with only helpers fails validation.
Adding a test tool takes three changes: the tool in the scorer's image, one `RUNNERS` entry, and a section in [Add an eval](../docs/add-an-eval.md).

| Kind | Files | Result |
| --- | --- | --- |
| Target | `target.yaml` | A reply check through Inspect's `match`, `pattern`, or `choice`. |
| Tests | `tests/` | Checks from Forge, including `compile`. |
| Rubric | `rubric.md` | One model verdict per named question, after the eval's other scorers. |

An eval can combine targets, tests, and a rubric. At least one scorer must exist.
Scorers run in target, tests, and rubric order.
Each returns check names mapped to `C` or `I` in `Score.value`.
`Score.metadata["reasons"]` holds the reasons.
`Score.explanation` shows the same reasons in Inspect's score panel.
Only a target scorer sets `Score.answer`.
The row exporter retains completed scores if a later scorer raises an error.

Target settings also drive the Hugging Face export.
`actors.quiz_solver_spec()` selects `generate` or `multiple_choice` for vanilla quizzes.
`checks.py` supplies scripted reference and empty solvers for the free check.
The reference pass applies the target's `reference` and overlays top-level `solution/` on the workspace.
An optional `solution/solution.s.sol` runs in the scorer container against the filtered chain RPC.
The free check skips rubric-only evals.

## Captured files and build scoring

`files.py` supplies one captured manifest for hashing, workspace files, and scorer inputs.
The eval hash covers file paths and bytes, including uncommitted author files.
It excludes timestamps, permissions, and local artifacts under the manifest's exclusion rules.
The loader rejects symlinks and hard links before it applies exclusions.
Later disk edits cannot alter an already loaded eval.

Build scoring stops the agent's processes before it captures the whole workspace.
Forge and the rubric share that snapshot.
The agent receives only the author's workspace files, including any `foundry.toml`.
The runner adds no compiler settings or library advice to the prompt.
The snapshot excludes `.git`, `out`, and `cache` at every depth.
Inside any `node_modules`, it keeps only `.sol` files.
The collector uses `find | tar`, without rsync.
The archive permits at most 50 MiB of contents and 20,000 files.

The scorer runs on the chain image and stays idle until grading.
It starts neither Anvil nor the RPC filter.
The scorer root mirrors the eval folder, with captured files under `workspace/` and the author's full folder under `scorer/`.
Tests import the agent's files by path, such as `workspace/src/BuilderPoints.sol`.
The generated `foundry.toml` sets both `src` and `test` to `scorer/tests`.
Forge compiles those tests and their imports.
Broken files that no test imports do not fail compilation.
One wrong import fails the whole `compile` check, with Forge's diagnostic as its reason.
The config disables FFI and automatic remappings.
It declares the `chain` RPC endpoint at `http://chain:8545` and permits reads of `chain.json` and `private.json`.

Every folder with `foundry.toml` or `package.json` is a project.
Foundry projects use only remappings that `forge remappings` accepts.
If that command fails, the project keeps only generated aliases.
Each npm package under a project's `node_modules` gets a remapping.
Every agent remapping has a context under its project folder, with deeper contexts first.
The runner rebases any declared context under that folder too.
Every project's `src/` imports resolve under its own `src/` folder.
The runner drops agent remappings for `forge-std` and `ds-test`.
The chain image ships forge-std at `/opt/solidity/lib/forge-std`; the agent image ships no Solidity libraries.
`hardhat/console.sol` maps to forge-std's console.
Other libraries come from the agent's workspace.

Neither image ships a Solidity compiler.
Forge detects and downloads the version required by each pragma, using the service's internet network.
A compiler download failure is an error that permits a retry, rather than a failed `compile` check.
A pragma that no released compiler satisfies fails `compile` with Forge's diagnostic.
An unexplained Forge timeout is also an error because the compiler download can consume that time.
Forge runs at the scorer root with `--root . --match-path 'scorer/tests/**' --json --no-storage-caching --build-info`.

Each test check takes its function name without arguments or a suite path.
A reverting setup produces `<Contract>.setUp`; a constructor failure produces `<Contract>.constructor`.
Reasons preserve Forge's assertion messages.
If inherited tests produce duplicate names, grading raises an error that names both suites.
The tests scorer runs each runner that claims a file and merges its checks.
One `compile` check passes only when every present runner builds.
Duplicate runtime names across runners raise an error that names both sources.

Every rubric receives the transcript.
If the tests compiled, the rubric asks the present runners for source evidence, before the transcript.
Forge supplies compiled files under `workspace/`.
Agent source precedes imported library source within that evidence.
That source includes imported agent libraries and excludes private tests and unused files.
If compilation failed, the rubric still receives the transcript.
Transcript evidence includes non-system message text, tool-call IDs, functions, arguments, results, and errors.
Transcript evidence drops reasoning, signatures, metadata, and tool views.
Evidence uses labeled source and transcript JSON with ASCII escapes and has no fixed byte cap.
The runner trims evidence only when Inspect's local token estimate exceeds the available context window.
The estimate counts the question, schema, message framing, and output allowance.
A single proportional cut retains the source prefix and transcript suffix, including the final reply.
The cut leaves a 20% margin on the available token estimate.
The cut can leave partial JSON. The grader must state uncertainty when evidence is incomplete.
Rubric checks take their `##` headings without a prefix.
The grader has no tools and returns one JSON object with `passed` and `reason`.
Two invalid replies produce an error; an empty reason produces a failed check.

## Results rows

`rows.jsonl` contains one JSON object per epoch, using schema version 5.
The board skips older rows.
The exporter writes atomically and skips unchanged content.

| Fields | Meaning |
| --- | --- |
| `schema_version` | Row format version. |
| `eval_id`, `eval_hash` | Eval identity. |
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

`config.yaml` supplies one `time_limit` and one `cost_limit` for every epoch.
Their defaults are 7200 seconds and $20.00.
The runner passes both limits directly to Inspect.
After the solver stops, Inspect gives scoring its own window of half the time limit.
A time limit still grades the agent's work. It does not cause an error or a retry.

The grader reserve covers the context window and configured output cap.
It covers two calls per question and three provider attempts per call.
`rubric_budget()` uses the largest configured input price without a cache discount.
Inspect's model info supplies the grader's context window.
An unknown context window stops planning with an error.
The configured Opus 5.5 grader has a 1,000,000-token window and reserves $32.94912 per question.
The direct Anthropic grader uses low effort and `max_tokens: 32768`, which includes thinking and the JSON verdict.
Each grader call has a total deadline that includes provider retry backoff.
The constants live beside the scorer implementation.

| Event | Row result |
| --- | --- |
| Incorrect answer, failed test, or negative rubric verdict | Failed check. |
| Agent cost limit | Failed check; further scoring work stops. |
| Agent time limit | Checks grade the work left by the agent. |
| Invalid submission or unsafe captured archive | Failed `compile` check. |
| Operator stop | Error. |
| Docker failure, memory failure, or setup failure | Error. |
| Grader provider failure or exhausted grader allowance | Error with any completed scorer results. |
| Forge output without results or a compiler diagnostic | Error. |
| Compiler download failure or unexplained Forge timeout | Error. |

Inspect retains the last 10 MiB of each exec stream.
Truncated Forge output can lack required results.
A Compose preparation failure records `preparation-errors.json` without consuming an epoch attempt.
A stock image-build failure stops the run with Docker's diagnostic.

Plans reserve a budget for every missing epoch.

## Compose and agents

An eval's optional `compose.yaml` declares extra services and named volumes.
The runner owns `default`, `scorer`, `chain`, and the networks.
Every extra service needs an image and a positive `mem_limit`; it joins only `work`.
Authors must pin extra-service images by digest; the runner does not enforce that rule.
The merged memory limits at configured concurrency must leave 1 GiB for the host.

Validation rejects privileged mode, host mounts, host namespaces, custom builds, and external volumes.
It also rejects inherited host environment values and host-variable interpolation.
The runner serializes the merged document to `inputs/<hash>/compose.yaml`.
Stock image tags come from [images/tag.py](ethevals/images/tag.py), independent of eval hashes.
Tags identify build inputs, not reproducible image bytes.

A declared chain selects `chain.compose.yaml`; an absent chain selects `stock.compose.yaml`.
The agent and chain share the internal `work` network.
The scorer and chain share the internal `grading` network.
Each service has its own internet network. The agent cannot resolve `scorer`.
Without a chain, the agent and scorer share no network.
Anvil's unfiltered RPC listens only on loopback inside the chain container.
The agent uses the filter at `http://chain:8545`.
[rpc_methods.json](ethevals/images/rpc_methods.json) classifies every RPC name and alias in pinned Anvil as `allow` or `deny`.
[rpc_filter.py](ethevals/images/rpc_filter.py) reads its allow list from that file and refuses every other method.
It allows wallet reads, polling filters, access lists, block receipts, simulations, and signed transaction calls.
It refuses `debug_*`, `trace_*`, `ots_*`, `txpool_*`, chain controls, and node signing.
Node-signing refusals say: "Sign locally and use eth_sendRawTransaction."
A batch with any refused method fails as a whole.
The filter rejects WebSockets; refusal messages enter the Inspect log.
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
`--epochs N` selects repeats 1 through N; `--epoch N` selects only repeat N.
`--epoch` requires one eval, one model or agent, and one mode. It cannot accompany `--epochs`.
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

## Setup and solution contract

Setup runs when `setup/setup.s.sol` exists, before the agent's time allowance starts.
The runner copies `setup/` and `workspace/` into the chain container's `/eval`.
Its Foundry config maps `forge-std/` and `ethevals/` and permits reads and writes of `chain.json` and `private.json`.
Forge installs the compiler each pragma requires.
The setup command has a 120-second timeout, or 600 seconds on a fork:

```sh
forge script setup/setup.s.sol --broadcast --slow --rpc-url http://127.0.0.1:8546
```

Setup inherits `ChainSetup` through `import {ChainSetup} from "ethevals/ChainSetup.sol";`.
Its constructor creates `chain.json` with `rpcUrl: "http://chain:8545"` and the chain ID, and an empty `private.json`.
The helper adds these functions:

| Function | Effect |
| --- | --- |
| `fund(addr, amount)` | Calls `anvil_setBalance` through `vm.rpc` to fund the real chain. |
| `chainRecord(name, value)` | Writes an address, uint, bytes32, or string field into `chain.json`. |
| `privateRecord(name, value)` | Writes the same value types into `private.json`. |

Each record call rewrites its file, so `run()` needs no lifecycle hooks.
`vm.deal` changes only Forge's simulation. `fund` changes the real chain.
Wallet creation and broadcasts use Foundry's `vm.createWallet`, `vm.randomUint`, and `vm.startBroadcast`.
Setup contracts can import contracts from `workspace/`, using only libraries shipped in `setup/` or `workspace/`.

The runner delivers `chain.json` to the agent's `/workspace/chain.json`.
The scorer receives an untouched copy of `chain.json` and the private file at its root, `/workspace`.
Validation rejects `workspace/chain.json` and `workspace/private.json`, because setup writes those files.
The free check applies the prompt-word lint to the delivered chain file.

Reference files under `solution/` overlay the agent's workspace at the same paths.
The script `solution/solution.s.sol` stays in the scorer container and reads `chain.json` from the scorer root.
It uses the agent's signing key and the same filtered RPC as the agent:

```sh
forge script solution/solution.s.sol --broadcast --rpc-url http://chain:8545
```

The solution command has a 120-second timeout.
After freezing the agent, the runner mines one block and captures the RPC refusal log before grading.
Forge tests read the finished chain with `vm.createSelectFork("chain")`.
Changes in the test's fork stay in Forge.

## Forks

Declare a network and a positive block number:

```yaml
chain: {fork: mainnet, block: 23819000}
```

The runner accepts `mainnet` and `base`.
It reads `MAINNET_RPC_URL` or `BASE_RPC_URL` from its environment.
A missing variable stops `run` before planning, providers, or containers start.
Use an archive RPC that serves the pinned block.

The saved compose file contains `${MAINNET_RPC_URL}` or `${BASE_RPC_URL}`, never its value.
Docker Compose resolves that value from the runner's environment when it starts the chain service.
Only that service receives the URL, and the filter passes it to Anvil.
The agent and scorer never receive the archive URL.
The agent's `chain.json` still names `http://chain:8545`.
The filter replaces the URL with `<fork rpc>` in RPC replies.
The runner does the same in the output of every container command before Inspect records it.

Anvil starts with `--fork-url`, `--fork-block-number`, and `--accounts 0`.
It keeps the real network's chain ID and has no prefunded accounts.
Setup funds the agent and prepares the chain before work starts.
Fork setup can impersonate a token holder with `vm.rpc("anvil_impersonateAccount", ...)`.
It sends the token transfer immediately through `vm.rpc("eth_sendTransaction", ...)` on the unfiltered Anvil.
It stops impersonation with `vm.rpc("anvil_stopImpersonatingAccount", ...)` before setup exits.
Generated wallets use signed Forge broadcasts for deployment.
The filter refuses `eth_sendTransaction` and node signing, so the agent cannot send from an impersonated holder.
The chain container gets 1 GiB on forks, compared with 256 MiB on fresh chains.
Setup and Forge tests each get 600 seconds, compared with 120 and 180 seconds on fresh chains.
The filter allows 60 seconds per upstream request on forks, compared with 15 seconds on fresh chains.
This gives Anvil time to fetch archive state on its first read.
Forge tests use `--no-storage-caching` to prevent state from an earlier fork from affecting checks.

`ethevals check` validates a fork eval even when its RPC variable is absent.
It then prints one reason and skips both the reference and untouched passes.
`scripts/ci.py checks` uses the same command and skip rule.
With the variable set, both passes run without model calls.

After reading a PR, dispatch [fork-check.yml](../.github/workflows/fork-check.yml) with its PR number and reviewed commit SHA:

```sh
gh workflow run fork-check.yml -f pr=<number> -f sha=<full commit SHA>
```

GitHub dispatches a workflow only when it is on the default branch, so `fork-check.yml` must be on `main`.
The workflow checks out that PR's head without saved credentials.
If the head differs from the reviewed SHA, the workflow fails before running PR code.
It checks every fork eval with the `MAINNET_RPC_URL` and `BASE_RPC_URL` secrets and posts a `fork check` status on the reviewed SHA.
The workflow has only content-read and status-write permissions.

## CI and publication

[checks.yml](../.github/workflows/checks.yml) runs free checks on pull requests without provider secrets.
[results.yml](../.github/workflows/results.yml) queues paid runs after `main` changes, excluding results-only changes.
It uses `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `OPENROUTER_API_KEY`, optional `EXA_API_KEY`, and the `ETHEVALS_BUDGET_USD` repository variable.
The matrix also receives `MAINNET_RPC_URL` and `BASE_RPC_URL` for fork evals.
A manual dispatch budget overrides that variable; the fallback budget is zero.
The job graph is `plan → matrix → publish`.
The plan job calls `ethevals plan` without provider keys and refuses work above the budget.
It saves the missing epochs, config, and restored results for the matrix jobs.
The plan checks out current `main`; the matrix and publisher use the SHA that the plan reports.
CI runs the first 256 missing epochs; a later run picks up the rest.
Each matrix job selects one epoch and uses a read-only token.
Each job builds both stock images with the GitHub Actions cache and loads them locally, without a registry.
The runner reuses local stock images whose tags match their build inputs.
Each job allows 240 minutes, including 120 for the agent, 60 for scoring, and 60 for builds, setup, and uploads.
The run step stops after 190 minutes and uploads available results even after failure.
A separate publisher holds no model keys and runs after failed or timed-out steps on `main`.
It downloads artifacts from every attempt of the workflow run. The next run resumes missing epochs.
For recovery, use "Re-run all jobs" instead of "Re-run failed jobs".

`scripts/ci.py plan-epochs` restores pending results, checks the budget, and emits the matrix.
Each matrix job calls `ethevals run --epoch N` with its row's selectors and the saved config and results.
`publish-results` rebuilds every artifact's rows and combines its logs into one release for the workflow run.
It writes one results commit with the planned log URLs before the upload starts.
If an upload stops, the rows remain recorded; the log URLs work after a successful upload retry.
It folds `origin/main`, `origin/ci/results`, and artifact rows onto current `main`.
The publisher updates the results pull request without a force push.
A retry can reopen a missing pull request without repeating a successful push.
If publication fails, rerun the workflow before starting another paid run to avoid paying for missing rows again.
Exhausted error epochs remain visible in the plan; a completed no-op succeeds.

`ethevals publish-logs --output DIR --repo OWNER/REPO --run-id ID --commit SHA` previews a log release.
Adding `--publish` uploads through `gh` and writes `DIR/published/results-ID.jsonl` after success.
It skips linked logs and non-final errors. The preview writes nothing.
CI tags the release at the workflow's source commit.

`ethevals export-hf --output DIR` writes vanilla quizzes to an empty directory.
It selects evals with `target.yaml`, vanilla mode, and no rubric.
It prints a reason for every skipped eval.
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
