# ETH Evals

ETH Evals measures what bare models know about Ethereum and how well agents do Ethereum work.

The runner uses Inspect for quizzes, Solidity builds, and chain transactions.
Claude Code runs in Docker in the internet mode. A separate container grades its code with Forge.

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

Quizzes have a 300-second limit. Builds have a 1,200-second limit.
The configuration gives the player a $5 cost budget.
The grader has separate model, effort, and output settings. Each model ID has one price schedule across both roles.
Config loading rejects conflicting prices for the same model ID.
Each grader request caps its serialized messages and generation settings at 300,000 bytes, including filenames and omission counts.
Its epoch allowance prices two calls per question at three bytes per input token and maximum output, without cache discounts.
At the configured prices, the two-question build allows $2.9096 for grading. Rows record this as `grader_cost_limit_usd`.
This allowance estimates input tokens. Inspect enforces it against reported usage.
Each grader call allows two provider retries with Inspect's backoff and a 60-second attempt timeout.
Inspect meters configured prices, including the lower price for cached reads. These prices are estimates until checked.
Limits stop further calls after usage arrives. An in-flight call can exceed its remaining budget.
Rows record each role's metered dollars and budget. The runner runs up to four tasks and samples at once.
An eval can override its time limit with `time_limit` in `eval.yaml`.
A runner, Docker, or grader failure produces `status: error`, with `passed: null`, and retries within the execution cap.
Grader errors include provider failures, exhausted budgets, and invalid replies after two calls.
Player time or cost limits fail the eval's checks and produce a final `status: failed` result.
These limits take precedence over scoring errors. The runner skips the snapshot and grader after a player limit.
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
Rows record the chain image ID and hashes of its Dockerfile and filter under `chain_inputs`.
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
Web search uses the keyless Exa MCP URL in `search_provider`. Claude Code's built-in WebSearch is disabled.
The Exa endpoint can rate-limit requests. Agents can also fetch pages and install packages from their containers.

Guess: the pair costs $1 to $5, including rubric grading. This estimate is not a spending cap.
The cost meter uses the configured prices. The time limit remains the main bound on a hung agent.

Inspect `results/adr0002/rows.jsonl` after both commands finish.
The quiz row has `harness: null` and the `erc_number` check.
The build row has `harness: claude_code`, eight `forge:` checks, and two `rubric:` checks with reasons.
The rubric's tokens and cost appear in `grader_tokens` and `grader_cost_usd`.
Rows with `status: error` need diagnosis. An agent's incorrect code has `status: failed`.
Before player epochs start, a key-free reference run discovers the seven test functions.
The cache includes the eval hash, image tag, Dockerfile, Foundry config, and check-naming version.
Names live under `inputs/<eval_hash>/<scoring_hash>/checks.json`. `forge:compile` completes the Forge check set.
Missing expected names after compilation are runner errors unless that suite's setup failed.
Discovery runs only for evals with missing epochs. Failures enter `discovery-errors.json`; other evals continue.
Compilation and setup failures retain that check set. Agent-added tests cannot add checks.
Forge and the rubric read one workspace snapshot after the runner stops the agent's processes.
The supplied `foundry.toml` defines grading settings and dependency remappings. Agent edits to it do not affect grading.
Scoring is offline with solc 0.8.30. The prompt and compilation failures list that available compiler.
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

These scripts run the real Claude Code binary with scripted `mockllm` responses:

```sh
env -u OPENROUTER_API_KEY uv run python inspect-runner/tests/prove_agent.py reference --output results/agent-reference
env -u OPENROUTER_API_KEY uv run python inspect-runner/tests/prove_agent.py empty --output results/agent-empty
```

The reference script sends a Bash tool call that writes the reference solution.
The empty script leaves the workspace untouched. Both run Forge and the scripted rubric grader.
The scripts assert the expected row status and named checks.
The Docker regression tests also cover hostile Compose environments and workspace contents:

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
The plan reports skipped rows by reason. It excludes key-free, stale-hash, and skills rows.
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
