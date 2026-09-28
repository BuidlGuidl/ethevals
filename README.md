# ETH Evals

ETH Evals measures what bare models know about Ethereum and how well agents do Ethereum work.

The runner uses Inspect for quizzes and Solidity builds.
Claude Code runs in Docker in the internet mode. A separate container grades its code with Forge.

## Install

Install Python 3.13 and [uv](https://docs.astral.sh/uv/getting-started/installation/).
From the repository root, run:

```sh
uv sync --frozen
```

Docker is required for builds and internet epochs. Vanilla quiz checks need no Docker.
Build the pinned Solidity image before the first build or internet epoch:

```sh
docker compose -f inspect-runner/ethevals/images/build.compose.yaml build default
```

The image includes Foundry 1.5.1, Solidity 0.8.30, and OpenZeppelin 5.4.0.

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

Inspect also accepts `ANTHROPIC_AUTH_TOKEN`, including a subscription token from `claude setup-token`.
Using that token this way is against Anthropic's terms.
This runner uses OpenRouter for paid calls and has no code path that uses a subscription token.

## Resume an interrupted command

Repeat the same command with the same output directory.
The runner reuses completed epochs and retries unfinished or errored epochs through Inspect.
The runner flushes each completed epoch to its log.
The same directory accepts changed evals and selections. Earlier logs remain available.
Each epoch is identified by its eval hash, agent, mode, and epoch number.
Price or grader changes never repeat completed agent work.
Rows retain the prices and grader used at execution time.

Quizzes have a 300-second limit. Builds have a 1,200-second limit.
The configuration caps each epoch at 500,000 total tokens and runs up to four tasks and samples at once.
An eval can override its time limit with `time_limit` in `eval.yaml`.
A crash or setup failure produces `status: error`, with `passed: null`, and runs again on the next invocation.
A time or token limit produces a named failed check and a final `status: failed` result.
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
The fixed `grader: opus` model answers the two rubric questions.
Web search uses the keyless Exa MCP URL in `search_provider`. Claude Code's built-in WebSearch is disabled.
The Exa endpoint can rate-limit requests. Agents can also fetch pages and install packages from their containers.

Guess: the pair costs $1 to $5, including rubric grading. This estimate is not a spending cap.
The token limit counts input and output tokens across calls. Current prices and caching affect the actual cost.

Inspect `results/adr0002/rows.jsonl` after both commands finish.
The quiz row has `harness: null` and the `erc_number` check.
The build row has `harness: claude_code`, seven `forge:` checks, and two `rubric:` checks with reasons.
The rubric's tokens and cost appear in `grader_tokens` and `grader_cost_usd`.
Rows with `status: error` need diagnosis. An agent's incorrect code has `status: failed`.
Compiler errors produce a failed `forge:compile` check.

To test resume, kill the build command during its first execution.
Repeat the same build command:

```sh
uv run ethevals run --evals evals/building/erc20-points-token --models opus --modes internet --epochs 1 --output results/adr0002
```

The finished quiz keeps its sample UUID. The unfinished build runs again.
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
