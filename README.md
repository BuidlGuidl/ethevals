# ETH Evals

ETH Evals measures what bare models know about Ethereum and how well agents do Ethereum work.

The runner uses Inspect for quizzes, Solidity builds, and chain transactions.
Claude Code, Codex CLI, and OpenCode run in Docker in the internet mode.
A separate container grades their code with Forge.

## Install

Install Python 3.13 and [uv](https://docs.astral.sh/uv/getting-started/installation/).
From the repository root, run:

```sh
uv sync --frozen
```

Docker is required for builds and internet epochs. Vanilla quiz checks need no Docker.
For build evals and internet quizzes, build the Solidity image before the first epoch:

```sh
docker compose -f inspect-runner/ethevals/images/stock.compose.yaml build default
```

The image includes Foundry 1.5.1, Solidity 0.8.30, OpenZeppelin 5.4.0, and forge-std 1.9.7.
The last two dependencies live in a root-owned directory. Submitted copies cannot replace them during grading.
It also supplies Node 20.11.0 and ripgrep for OpenCode. Rebuild the image after pulling runner changes.
Both image names hash their Dockerfile and copied files. Grading settings in `foundry.toml` do not rename an image.
The runner hashes `Dockerfile` and `solc.json`. The chain hashes `Chain.Dockerfile`, `solc.json`, and `rpc_filter.py`.
`solc.json` supplies the compiler version, URLs, and checksums for both images and the runner's compiler list.
Preparation rejects a declared stock image name that differs from its computed name.
After changing build inputs, run `uv run python inspect-runner/ethevals/images/tag.py`.
Use its output in `stock.compose.yaml` and `act.compose.yaml`, then rebuild.
These names identify inputs, not image bytes. The runner's apt packages remain unpinned, so fresh builds can differ.

## Run without a key

```sh
env -u OPENROUTER_API_KEY uv run ethevals check
env -u OPENROUTER_API_KEY uv run pytest
```

`check` runs each quiz's reference answer and each build or act reference solution for three epochs.
It repeats the pipeline with empty answers, untouched workspaces, and untouched chains.
The command succeeds only when every reference passes and every untouched case fails.
It makes no paid call. Rubrics do not run in `check`.
Every invocation runs fresh, including when its output folder already contains logs.
For `match` and `choice`, the reference check only proves that the target matches itself.
Pattern quizzes can declare a formatted `reference` reply in `scorer/scorer.yaml`.

Results go to `results/reference/rows.jsonl` and `results/empty/rows.jsonl`.
Their `logs/` folders hold the full Inspect logs.
Mock token counts are synthetic. Mock cost is zero.

To check one folder or choose an answer:

```sh
env -u OPENROUTER_API_KEY uv run ethevals validate --evals evals/concepts/agent-registries
env -u OPENROUTER_API_KEY uv run ethevals run --answer default --output results/default
```

`run` succeeds when execution succeeds, even when an answer fails its checks.
`check` also enforces the expected verdicts.

## Run with OpenRouter

The paid models and their prices are guesses in [config.yaml](inspect-runner/ethevals/config.yaml).
Check their slugs, effort, and prices before a paid epoch.
Set `OPENROUTER_API_KEY` in your shell.
Then run:

```sh
uv run ethevals run --output results/paid
```

The default selects all four configured models and three epochs for every quiz in the vanilla mode.
To select a subset, use `--evals`, `--models opus codex`, `--modes vanilla`, or `--epochs 1`.
Use `--config path/to/config.yaml` for a separate configuration.

To run all four agents on the ERC-20 build and both quizzes in the internet mode:

```sh
uv run ethevals run --evals evals/building/erc20-points-token evals/concepts/agent-registries evals/concepts/wei-per-ether --models opus codex kimi glm --modes internet --epochs 1 --output results/four-agents
```

To run all four bare models on both quizzes in the vanilla mode:

```sh
uv run ethevals run --evals evals/concepts/agent-registries evals/concepts/wei-per-ether --models opus codex kimi glm --modes vanilla --epochs 1 --output results/four-models
```

Guess: these commands together cost $5 to $20, including build rubric grading.
This guess is not a spending cap. Actual slugs, prices, and paid model behavior remain untested.

The agents use Claude Code 2.1.274, Codex CLI 0.158.0, and OpenCode 1.18.33.
Kimi and GLM share OpenCode. All four models default to high effort in the configuration.

| Agent | CLI identity | CLI effort setting |
| --- | --- | --- |
| Claude Code | `claude-opus-5-5` | `CLAUDE_CODE_EFFORT_LEVEL=high` |
| Codex CLI | `gpt-6-sol` | `model_reasoning_effort="high"` |
| OpenCode with Kimi | `openrouter/moonshotai/kimi-k3` | Model option `reasoning.effort=high` |
| OpenCode with GLM | `openrouter/z-ai/glm-5.3` | Model option `reasoning.effort=high` |

`agent_model_config` selects each CLI's identity. OpenCode selects its Kimi prompt for Kimi and its default prompt for GLM.
Its provider definitions live in [opencode-models.json](inspect-runner/ethevals/images/opencode-models.json).
Both use OpenRouter's `top_provider` limits of 1,048,576 context tokens and 943,718 output tokens, checked September 28, 2026.
These are catalog limits. They do not promise that every routed provider supports the same limits.
Source: [OpenRouter model catalog](https://openrouter.ai/api/v1/models).
The container gets a dummy OpenRouter credential. Inspect routes model calls to the configured host-side model.

Inspect also sets the configured backend effort. Its default bridge drops the CLI's generation settings before that step.
The proofs record the raw CLI requests separately, so the backend setting cannot conceal a missing CLI effort.
Codex uses code mode. A model adapter repairs Inspect 0.3.271's custom-call conversion while preserving its event consumer.
It converts only declared custom calls with exactly one string `input` and no parse error.
All agent factories set refusal retries to zero. Inspect's provider retries remain separate.

Each agent gets the Exa HTTP MCP server from `search_provider`.
Claude Code disallows `WebSearch`, and Codex sets `web_search="disabled"`.
These settings keep search on Exa instead of each provider's hosted search API.
OpenCode 1.18.33 does not register `websearch` for OpenRouter unless its optional search flags are enabled.
Its built-in search also calls keyless Exa. The runner leaves its optional search flags unset.
Claude Code retains `WebFetch`; OpenCode retains `webfetch`. Codex has no native page-fetch tool.
All four agents retain Exa search and fetch, plus a shell with network access.
Exa's keyless endpoint can rate-limit concurrent agents.
Set `EXA_API_KEY` to authenticate the configured `mcp.exa.ai` endpoint.
Rows count search calls, failed results, and rate-limited results in `search_calls`, `search_failed`, and `search_rate_limited`.

Inspect also accepts `ANTHROPIC_AUTH_TOKEN`, including a subscription token from `claude setup-token`.
Using that token this way is against Anthropic's terms.
This runner uses OpenRouter for paid calls and has no code path that uses a subscription token.

## Resume an interrupted command

Repeat the same command with the same output directory.
The runner reuses completed epochs. Each identity permits at most two executions, including unfinished or errored executions.
After fixing an error, add `--retry-errors` to grant each selected error epoch one further attempt.
The flag preserves completed passes and failures.
The runner flushes each completed epoch to its log.
The same directory accepts changed evals and selections. Earlier logs remain available.
Each epoch is identified by its eval hash, agent, mode, and epoch number.
Price or grader changes never repeat completed agent work.
Rows retain the prices and grader used at execution time.

Quizzes allow 300 seconds of working time. Builds and acts allow 1,200 seconds.
Inspect excludes provider retry backoff and sandbox waits from working time.
The wall-clock backstop is three times the working limit: 900 seconds for quizzes and 3,600 seconds for builds and acts.
The configuration gives the player a $5 cost budget.
The grader has separate model, effort, and output settings. Each model ID has one price schedule across both roles.
Config loading rejects conflicting prices for the same model ID.
Each grader request caps its serialized messages and generation settings at 300,000 bytes, including filenames and omission counts.
Evidence uses ASCII escapes. The allowance reserves one input token per serialized byte and the maximum output for every provider attempt.
Each question permits two generation calls, each with two retries: at most six provider attempts per question.
The formula is `questions * 2 * 3 * (300000 * max(input, cache_read, cache_write) + max_tokens * output) / 1000000`.
At the configured prices, the two-question build reserves $23.7288. Rows record this ceiling as `grader_cost_limit_usd`.
Inspect meters completed requests separately. The ceiling also covers abandoned attempts that do not appear in usage.
Each grader call has a 60-second total deadline, including backoff, and a 20-second attempt timeout.
The two-question build permits 240 seconds of grading plus 180 seconds of Forge execution.
Scoring has a 540-second total deadline, including 120 seconds for snapshot and transfer work.
Act scoring has a 240-second total deadline, including its 120-second check script and 120 seconds for capture and transfer.
Task creation rejects scoring bounds that cannot fit inside Inspect's scoring window, half the wall-clock backstop.
Inspect meters configured prices, including the lower price for cached reads. These prices are estimates until checked.
Limits stop further calls after usage arrives. An in-flight call can exceed its remaining budget.
Rows record each role's metered dollars and budget. The runner runs up to four tasks and samples at once.
An eval can override its time limit with `time_limit` in `eval.yaml`.
A runner, Docker, or grader failure produces `status: error`, with `passed: null`, and retries within the execution cap.
Grader errors include provider failures, exhausted budgets, and invalid replies after two calls.
Player working-time or cost limits fail the eval's checks and produce a final `status: failed` result.
These limits take precedence over scoring errors. The runner skips the snapshot and grader after a player limit.
An operator stop or a wall-clock stop before the working limit produces `status: error`.
An incorrect answer produces `status: failed`, with `passed: false`.

## Read the runner contracts

[The runner reference](inspect-runner/README.md) describes eval folders, results rows, and extension hooks.
[CONTEXT.md](CONTEXT.md) defines the project terms.

## Write an act eval

Copy [send-six-decimal-token](evals/transactions/send-six-decimal-token) into `evals/transactions/<name>/`.
Set `type: act`, `modes: [internet]`, and a prompt in `eval.yaml`.
Declare `scorers: [{kind: check_script}]` in `scorer/scorer.yaml`.
Keep the starting files under `workspace/`.

Write `scorer/setup.py` to prepare the chain before the agent starts.
Use a fresh key, fund it, and deploy the task's contracts.
The script returns JSON with a `files` mapping of workspace paths to text.
The fixture supplies `chain.json` with the key, contract addresses, and `http://chain:8545`.
Setup and check code stay in the chain container. Only those selected output files reach the agent.
Setup has its own 120-second script limit and a 150-second total limit, including file transfer.
Setup consumes neither the player's time allowance nor its recorded working time. Setup failures and timeouts are errors.

Write `scorer/check.py` to print named checks with boolean `passed` and a one-line `reason`.
Write `scorer/solution/run.sh` to sign and send through the public RPC URL, using the supplied key.
The reference runs in the offline scorer, which also receives the workspace and setup's selected files.
Author scripts can reach the private containers. They cannot reach the host or internet.
Compose requires `internal: true` and `com.docker.network.bridge.inhibit_ipv4: "true"` on the private network.
The runner discovers check names from that reference before any agent epoch.
Wrong amounts, missing verdicts, and crashed check scripts keep the same check set.

The stock chain uses Anvil 1.5.1 behind an RPC allowlist in the same container.
Anvil listens on localhost. The agent can read chain state and send signed raw transactions through the filter.
It cannot use unlocked sends, unsigned sends, signing methods, WebSockets, or chain controls.
A namespace blocklist misses `eth_sendUnsignedTransaction`, which moves value without a key.
The runner stops the agent's processes once, then closes the filter.
The request already forwarding finishes. Waiting requests fail.
Capture disables mining, clears the pool, and waits for an empty block after any active mining.
The check reads the state at that final block. No interval mining runs.

The chain image builds independently of the runner image.
It uses digest-pinned Python 3.13.7 and Foundry 1.5.1 images, plus checksum-pinned solc 0.8.30 for each architecture.
The runner builds both images for act evals. A build failure becomes that eval's discovery error with Docker's message.
Rows record both input-based image names under `images`.
`runner_inputs` and `chain_inputs` record SHA-256 hashes of each image's build files, including the shared compiler manifest.
Then run the free check:

```sh
env -u OPENROUTER_API_KEY -u ANTHROPIC_API_KEY -u OPENAI_API_KEY -u ANTHROPIC_AUTH_TOKEN \
  uv run ethevals check --evals evals/transactions/send-six-decimal-token
```

The reference must pass every check. The untouched chain must fail the epoch.
[The act contract](inspect-runner/README.md#act-scoring) gives script paths, limits, and failure rules.

## Run the paid ADR 0002 test

Set `OPENROUTER_API_KEY` in your shell and build the image as above.
Check the guessed model slug and prices in `inspect-runner/ethevals/config.yaml` before paying.
Run these two commands from the repository root:

```sh
uv run ethevals run --evals evals/concepts/agent-registries --models opus --modes vanilla --epochs 1 --output results/adr0002
uv run ethevals run --evals evals/building/erc20-points-token --models opus --modes internet --epochs 1 --output results/adr0002
```

The quiz uses bare Opus 5.5. The build uses Claude Code 2.1.274 with Opus 5.5 and high effort.
The separate `grader` configuration selects the model that answers the two rubric questions.
Web search uses the Exa MCP URL in `search_provider`, with an optional `EXA_API_KEY`. Claude Code's built-in WebSearch is disabled.
The Exa endpoint can rate-limit requests. Agents can also fetch pages and install packages from their containers.

Guess: the pair costs $1 to $5, including rubric grading. This estimate is not a spending cap.
The cost meter uses the configured prices. Working time bounds player work; the wall-clock backstop bounds a hung agent.

Inspect `results/adr0002/rows.jsonl` after both commands finish.
The quiz row has `harness: null` and the `erc_number` check.
The build row has `harness: claude_code`, eight `forge:` checks, and two `rubric:` checks with reasons.
The rubric's tokens and cost appear in `grader_tokens` and `grader_cost_usd`.
Rows with `status: error` need diagnosis. An agent's incorrect code has `status: failed`.
Before player epochs start, a key-free reference run discovers the seven test functions.
The cache includes the eval hash, service image names, computed stock image names, grading config, and check-naming versions.
An edit to `foundry.toml` invalidates discovered checks without renaming either image.
Names live under `inputs/<eval_hash>/<scoring_hash>/checks.json`. `forge:compile` completes the Forge check set.
Missing expected names after compilation are runner errors unless that suite's constructor or `setUp()` failed.
Discovery runs only for evals with missing epochs. Failures append to `discovery-errors.json`; other evals continue.
Discovery errors name failed tests and compiler diagnostics.
Compilation and suite lifecycle failures retain that check set. Agent-added tests cannot add checks.
Signal exits and Forge output without results or a compiler diagnostic are runner errors.
Forge streams through capped readers. The wrapper waits for both reader processes before the scorer reads their files.
The cap is 10 MiB per stream, with one extra byte to detect overflow.
Compilation reasons use the coded diagnostic, without source frames. Only compiler-version failures include the offline compiler note.
Forge and the rubric read one workspace snapshot after the runner stops the agent's processes.
The supplied `foundry.toml` defines grading settings and dependency remappings. Agent edits to it do not affect grading.
Scoring is offline with solc 0.8.30. The prompt and compiler-version failures list that available compiler.
The scorer container has no internet network. Compiler downloads happen only when the image builds.
The rubric reads Forge's compiled source records, with the agent's `src/` files first.
It excludes unused libraries, private tests, and the runner's libraries.
The grader receives the files that fit the request cap and a count of omitted files.
The evidence block carries Inspect's cache marker and stays identical across the rubric questions.
The parser accepts one JSON verdict, with optional Markdown fences. Prose or quoted verdicts count as invalid replies.
Missing evidence does not replace the grader's verdict.

The `tests` scorer supplies Foundry files and the build prompt note. Internet quizzes receive neither.
Authors must omit `workspace/foundry.toml`; the runner supplies it.

To test resume, kill the build command during its first execution.
Repeat the same build command:

```sh
uv run ethevals run --evals evals/building/erc20-points-token --models opus --modes internet --epochs 1 --output results/adr0002
```

The finished quiz keeps its sample UUID. The unfinished build runs again if its execution cap allows it.
Repeating either finished command reuses its row, including a final failed result.
ADR 0002 remains proposed until this paid test succeeds.

## Prove the agent path without a key

These scripts run a real agent binary with scripted `mockllm` responses:

```sh
env -u OPENROUTER_API_KEY -u ANTHROPIC_API_KEY -u OPENAI_API_KEY -u ANTHROPIC_AUTH_TOKEN uv run python inspect-runner/tests/prove_agent.py reference --model codex --output results/codex-reference
env -u OPENROUTER_API_KEY -u ANTHROPIC_API_KEY -u OPENAI_API_KEY -u ANTHROPIC_AUTH_TOKEN uv run python inspect-runner/tests/prove_agent.py empty --model codex --output results/codex-empty
```

Select `opus`, `codex`, `kimi`, or `glm` with `--model`. The default is `opus`.
The reference script sends a shell tool call that writes the reference solution.
The empty script leaves the workspace untouched. Both run Forge and the scripted rubric grader.
Each proof makes one real Exa search and checks its result.
The scripts check row status, named checks, raw CLI effort, and absence of built-in search.
OpenCode proofs also check its model identity and selected system prompt.
`cli-requests.jsonl` records the CLI requests before Inspect merges model settings.
The Docker tests run both scripts for all four agents, plus the existing Compose and workspace proofs:

```sh
env -u OPENROUTER_API_KEY -u ANTHROPIC_API_KEY -u OPENAI_API_KEY -u ANTHROPIC_AUTH_TOKEN uv run pytest -q --run-docker -m docker
```

## Build the results board

From `site/`, run `pnpm install --frozen-lockfile && pnpm build` with Node.js 22 or later.
Real builds also require uv and Python 3.13 to export the runner's eval catalog.
The board reads `results/rows.jsonl` by default. `ETHEVALS_ROWS` selects another rows file.
The site accepts schema v3 rows and uses the runner's catalog for declarations and hashes.
The static export goes to `site/out/`. Without real rows, it shows an empty state.
Use `ETHEVALS_SAMPLE=1 pnpm build` for the labelled sample board.
[The site README](site/README.md) covers viewing the sample, results paths, and log URLs.

## Publish full logs

Publish one GitHub release per results run. Only unpublished logs for rows the site shows become assets.
Choose a unique run ID, such as a CI run ID and attempt number.
Use the full source commit SHA as `--commit`.

```sh
uv run ethevals publish-logs --output results/paid \
  --repo BuidlGuidl/ethevals --run-id 12345-1 --commit FULL_COMMIT_SHA --dry-run
```

The default is a dry run. It writes nothing and makes no network calls.
It prints a JSON plan with the release tag, the `gh` command, and each asset's rows and URL.
The plan reports skipped rows by reason. It excludes key-free, stale-hash, skills, and non-final error rows.
The command loads current eval hashes from `evals/*/*`. Use `--evals` and `--config` to select other evals or settings.
It skips release-linked rows and logs named in earlier `published/results-*.jsonl` files.
Keep those files when reusing a results folder. An empty plan creates no release or rows file.

To publish that run, repeat the command with `--publish` instead of `--dry-run`.
The command uses your authenticated `gh` session to create the release and upload its assets.
After the upload succeeds, it writes `results/paid/published/results-12345-1.jsonl`.
Each linked row stores `results-12345-1/<filename>.eval` in `log_file`.
The original rows and logs stay available for resume. A failed publish writes no linked rows.
It sets `--latest=false` so results releases do not replace a software release marked latest.
It refuses missing logs, unsafe asset names, paths containing `#`, more than 1,000 assets, and files of 2 GiB or more.
An existing release tag makes `gh release create` fail. The command never replaces existing assets.
After a partial upload failure, inspect the release before retrying. Use a new run ID for a replacement release.

Install the linked rows in the site's results file only after publication succeeds.
Set `ETHEVALS_LOG_BASE=https://github.com/BuidlGuidl/ethevals/releases/download` when building the site.
That base reaches every results release. A link downloads the full `.eval` file.
Save the file in a local folder, then run `uv run inspect view --log-dir path/to/folder`.
A private repository requires GitHub access to download its assets. Public log downloads require a public repository.

## Export the vanilla quiz dataset

```sh
uv run ethevals export-hf --output out/hf \
  --hf-repo ethereum-foundation/hf-ethevals-dataset
```

Use an empty output directory. The command writes JSONL data, an HF dataset card, and `eval.yaml`.
It prints the row count, config names, skipped evals with reasons, repository setting, and license as JSON.
It makes no model calls and uploads nothing. Keep result logs outside this directory.
Set `ETHEVALS_HF_REPO` or pass `--hf-repo` to choose the dataset repository.
The license is undecided. Set `ETHEVALS_DATASET_LICENSE` or pass `--license` after choosing an HF license identifier.

Each row has `id`, `input`, `target`, `choices`, and `metadata` with the eval ID, pillar, and eval hash.
Only quizzes that declare vanilla mode enter the export.
Each config groups a pillar and one set of scorer settings under `data/<config>/test.jsonl`.
Names spell out scorer settings, such as `concepts-choice` and `concepts-match-exact`. Only pattern configs use a regex hash.
The card marks the first config as the default and computes its size category from the exported row count.
Match tasks set `location` explicitly to preserve the runner's verdicts.
The loader rejects blank choices. Vanilla quizzes must have one target scorer and one accepted answer.
`validate`, `check`, and `export-hf` enforce that export rule before any run or export.
It accepts single-item target lists as strings. It never drops an unsupported vanilla quiz silently.

Load a local data file without a field mapping:

```python
from inspect_ai.dataset import json_dataset

dataset = json_dataset("out/hf/data/CONFIG/test.jsonl")
```

Replace `CONFIG` with a config name printed by the export.
After publication, the same fields load through `hf_dataset` without a mapping:

```python
from inspect_ai.dataset import hf_dataset

dataset = hf_dataset("ethereum-foundation/hf-ethevals-dataset", name="CONFIG", split="test", revision="VERSION")
```

The remote loader needs Inspect's optional `datasets` package. The export and local proof do not need it.
The dataset card also gives the stock `inspect eval hf/<owner>/<repo>` command.
That command reads each task's solver and scorer from `eval.yaml` and calls the model you select.
It needs `huggingface_hub` and `datasets`.

Run the local proof without provider keys:

```sh
env -u OPENROUTER_API_KEY -u ANTHROPIC_API_KEY -u OPENAI_API_KEY -u ANTHROPIC_AUTH_TOKEN \
  uv run ethevals prove-hf --export out/hf --output out/hf-proof
```

The proof calls Inspect's `task_create_from_hf` with local replacements for Hub downloads and dataset reads.
Inspect resolves the solver and scorer specs itself. The proof also checks default JSONL loading against the runner.
The runner and exporter share `target_scorer_spec` in `scorers.py` and `quiz_solver_spec` in `actors.py`.
Reference answers must pass. Wrong answers must fail.
It records observed verdicts in `out/hf-proof/report.json` and prints them as JSON.
Proof logs must stay outside the dataset directory. Pytest runs the same proof.
The hosted `hf/` download path remains untested until the dataset exists on HF.
