# ETH Evals

ETH Evals measures what bare models know about Ethereum and how well agents do Ethereum work.
The runner uses Inspect and grades each eval with a target, Forge tests, a rubric, or several of these.
Claude Code, Codex CLI, and OpenCode run in Docker.

The board separates agent results from bare-model knowledge.
See [the glossary](CONTEXT.md) for terms and [the decisions](docs/adr/) for the system's design.

## Install

Install Python 3.13 and [uv](https://docs.astral.sh/uv/getting-started/installation/).
From the repository root, run:

```sh
uv sync --frozen
```

Docker is required for internet and skills epochs.
Vanilla quizzes need no containers.
The runner builds its images before the first sandbox epoch in each run.

## Run the free check

Strip provider credentials before a free check:

```sh
env -u OPENROUTER_API_KEY -u ANTHROPIC_API_KEY -u OPENAI_API_KEY \
  -u ANTHROPIC_AUTH_TOKEN -u EXA_API_KEY uv run ethevals check
```

`check` runs reference answers and solutions, then empty answers and untouched workspaces.
It succeeds only when every reference passes and every untouched case fails.
It makes no paid calls and skips rubric grading.
The configured epoch count applies to both cases.
Every invocation runs fresh, even when the output folder already contains logs.

Results go to `results/check/reference/rows.jsonl` and `results/check/empty/rows.jsonl`.
Each case has a `logs/` folder with full Inspect logs.
These check results stay separate from the board's paid results.

To check one eval, select its folder:

```sh
uv run ethevals check --evals evals/concepts/agent-registries
```

To check the folder format without execution, replace `check` with `validate`.
For new evals, follow [Add an eval](docs/add-an-eval.md).

## Run with provider keys

Read [Plan and run](inspect-runner/README.md#plan-and-run) for budgets, keys, and resume options.
[ADR 0006](docs/adr/0006-direct-provider-keys-and-native-search.md) records the provider and search decisions.

For a first paid Claude Code test, set `ANTHROPIC_API_KEY` and run:

```sh
uv run ethevals run --evals evals/concepts/agent-registries evals/transactions/send-six-decimal-token --agents claude-code-opus-5.5 --modes internet --epochs 1 --budget 100
```

## Open the board

The agent table shows internet results by harness, model, and effort.
The knowledge table shows vanilla quiz results for bare models.
Open a cell to read its prompt, epoch checks, costs, and published log links.

From `site/`, start the local board:

```sh
pnpm install --frozen-lockfile
pnpm run dev
```

Open the local URL printed by Next.js, normally <http://localhost:3000>.
Without results, the board shows its empty state and eval catalog.
See [the site guide](site/README.md) for demo data, settings, and site checks.

Runner maintainers can use [the runner reference](inspect-runner/README.md) for scoring, limits, rows, and CI.
