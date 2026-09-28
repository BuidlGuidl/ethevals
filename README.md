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
Inspect's `eval_set` reuses completed epochs and retries unfinished or errored epochs.
The runner flushes each completed epoch to its log.
A changed eval hash, selection, or model configuration needs a new output directory.
Keep old directories if their results must remain available.

Each epoch has a 300-second limit from the configuration.
A crash, a setup failure, or a limit produces `status: error`, with `passed: null`.
An incorrect answer produces `status: failed`, with `passed: false`.

## Read the runner contracts

[The runner reference](inspect-runner/README.md) describes eval folders, results rows, and the hooks for step 2b.
[CONTEXT.md](CONTEXT.md) defines the project terms.
