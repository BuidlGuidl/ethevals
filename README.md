# ETH Evals

ETH Evals measures what bare models know about Ethereum and how well agents do Ethereum work.
The runner uses Inspect for quizzes, Solidity builds, and chain transactions.
Claude Code, Codex CLI, and OpenCode run in Docker.

The board separates agent results from bare-model knowledge.
See [the glossary](CONTEXT.md) for terms and [the decisions](docs/adr/) for the system's design.

## Install

Install Python 3.13 and [uv](https://docs.astral.sh/uv/getting-started/installation/).
From the repository root, run:

```sh
uv sync --frozen
```

Docker is required for builds, acts, and internet epochs.
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

## Plan a paid run

Check model names, effort settings, and prices in [config.yaml](inspect-runner/ethevals/config.yaml).
The checked-in prices are guesses.
Use `--config path/to/config.yaml` for a separate configuration.

Print the missing work without keys, Docker, or model calls:

```sh
uv run ethevals plan --models opus-5.5 --agents claude-code-opus-5.5 --modes vanilla internet --epochs 1 --budget 100
```

`--budget` is a USD ceiling for the plan's cost reserve.
The plan includes agent, grader, search, and remaining error attempts.
A plan that exceeds the budget exits with code 1.
The runner rejects that plan before it constructs providers or prepares containers.

Cost limits use configured prices and check usage after calls.
An in-flight call can exceed the remaining allowance.
The budget reserve is not a provider billing cap.

## Run with OpenRouter

Set `OPENROUTER_API_KEY` in your shell, then run the selected plan:

```sh
uv run ethevals run --models opus-5.5 --agents claude-code-opus-5.5 --modes vanilla internet --epochs 1 --budget 100
```

Use `--evals` to select folders and `--output` to choose a results directory.
`--models` selects bare models for vanilla; `--agents` selects agents for internet and skills.
Each selector requires a matching mode. Without selectors or mode flags, the runner selects every model, agent, and mode.
`--effort low|medium|high|xhigh` overrides model and agent effort for that invocation.
Omit a model's `effort` in the config to use its provider's default; rows then record `effort: null`.
Each eval runs only in modes it declares.
The skills mode adds the repo's Ethereum skills pack to the internet mode. The scenario type is not supported yet.

`run` succeeds when execution succeeds, even when an agent fails its checks.
Repeat the command to resume missing epochs.
Completed passes and failures remain final.
Errors can run again within `max_attempts`; `--retry-errors` grants one further execution per selected error epoch.
The runner reads committed results from `results/rows.jsonl` by default.
Use `--rows` to select a different resume file.

The full transcript stays in the Inspect log.
To browse a local run, use:

```sh
uv run inspect view --log-dir results/logs
```

## Open the board

The agent table shows internet results by harness, model, and effort.
The knowledge table shows vanilla quiz results for bare models.
Open a cell to read its prompt, epoch checks, costs, and published log links.

From `site/`, build the static board:

```sh
pnpm install --frozen-lockfile
pnpm build
python3 -m http.server 8000 --directory out
```

Open <http://localhost:8000>.
Without results, the board shows its empty state and eval catalog.
See [the site guide](site/README.md) for demo data, settings, and site checks.

Runner maintainers can use [the runner reference](inspect-runner/README.md) for scoring, limits, rows, and CI.
