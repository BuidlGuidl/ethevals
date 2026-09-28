# ETH Evals

ETH Evals measures what bare models know about Ethereum and how well agents do Ethereum work.

The runner uses Inspect for quizzes and Solidity builds.
Claude Code, Codex CLI, and OpenCode run in Docker in the internet mode.
A separate container grades their code with Forge.

## Install

Install Python 3.13 and [uv](https://docs.astral.sh/uv/getting-started/installation/).
From the repository root, run:

```sh
uv sync --frozen
```

Docker is required for builds and internet epochs. Vanilla quiz checks need no Docker.
Build the pinned Solidity image before the first build or internet epoch:

```sh
docker compose -f inspect-runner/ethevals/images/stock.compose.yaml build default
```

The image includes Foundry 1.5.1, Solidity 0.8.30, OpenZeppelin 5.4.0, and forge-std 1.9.7.
The last two dependencies live in a root-owned directory. Submitted copies cannot replace them during grading.
It also supplies Node 20.11.0 and ripgrep for OpenCode. Rebuild the image after pulling runner changes.
The image tag hashes `Dockerfile` and `foundry.toml`. Tests reject a tag that no longer matches those inputs.
After changing either input, run `uv run python inspect-runner/ethevals/images/tag.py`.
Use its output for both image tags in `stock.compose.yaml`, then rebuild.

## Run without a key

```sh
env -u OPENROUTER_API_KEY uv run ethevals check
env -u OPENROUTER_API_KEY uv run pytest
```

`check` runs each quiz's reference answer and the build's reference solution for three epochs.
It repeats the pipeline with empty answers and the untouched build workspace.
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
The grader has separate model, effort, output, and price settings.
Its epoch budget covers two full-evidence calls per question, with `grader_cost_limit` as a minimum.
Inspect meters configured prices, including the lower price for cached reads. These prices are estimates until checked.
Limits stop further calls after usage arrives. An in-flight call can exceed its remaining budget.
Rows record each role's metered dollars and budget. The runner runs up to four tasks and samples at once.
An eval can override its time limit with `time_limit` in `eval.yaml`.
A runner, Docker, or grader failure produces `status: error`, with `passed: null`, and retries within the execution cap.
Grader errors include provider failures, exhausted budgets, and invalid replies after two calls.
Player time or cost limits fail the eval's checks and produce a final `status: failed` result.
An incorrect answer produces `status: failed`, with `passed: false`.

## Read the runner contracts

[The runner reference](inspect-runner/README.md) describes eval folders, results rows, and extension hooks.
[CONTEXT.md](CONTEXT.md) defines the project terms.

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
The runner caches them by eval hash under `inputs/<hash>/checks.json`. `forge:compile` completes the Forge check set.
Compilation and setup failures retain that check set. Agent-added tests cannot add checks.
Forge and the rubric read one workspace snapshot after the runner stops the agent's processes.
The supplied `foundry.toml` defines grading settings and dependency remappings. Agent edits to it do not affect grading.
The rubric reads Forge's compiled source records, with the agent's `src/` files first.
It excludes unused libraries, private tests, and the runner's libraries.
The grader receives the files that fit the evidence cap and a list of omitted files.
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
