# ETH Evals

ETH Evals measures what bare models know about Ethereum and how well agents do Ethereum work.

The runner uses Inspect. It currently runs quizzes in the vanilla mode.
The internet mode and build evals arrive in step 2b.

## Install

Install Python 3.13 and [uv](https://docs.astral.sh/uv/getting-started/installation/).
From the repository root, run:

```sh
uv sync --frozen
```

Docker is required for the agent spike and future internet epochs. Quiz checks need no Docker.

## Run without a key

```sh
env -u OPENROUTER_API_KEY uv run ethevals check
env -u OPENROUTER_API_KEY uv run pytest
```

`check` sends each quiz's reference answer through Inspect's mock model, solver, and scorer for three epochs.
It repeats the pipeline with empty answers. The command succeeds only when every reference passes and every empty answer fails.
It makes no paid call, including to the grader.
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

Each epoch has a 300-second limit from the configuration.
A crash or setup failure produces `status: error`, with `passed: null`, and runs again on the next invocation.
A time or token limit produces a named failed check and a final `status: failed` result.
An incorrect answer produces `status: failed`, with `passed: false`.

## Read the runner contracts

[The runner reference](inspect-runner/README.md) describes eval folders, results rows, and the hooks for step 2b.
[CONTEXT.md](CONTEXT.md) defines the project terms.

## Build the results board

From `site/`, run `pnpm install --frozen-lockfile && pnpm build` with Node.js 22 or later.
Real builds also require uv and Python 3.13 to export the runner's eval catalog.
The board reads `results/rows.jsonl` by default. `ETHEVALS_ROWS` selects another rows file.
The static export goes to `site/out/`. Without real rows, it shows an empty state.
Use `ETHEVALS_SAMPLE=1 pnpm build` for the labelled sample board.
[The site README](site/README.md) covers viewing the sample, results paths, and log URLs.
