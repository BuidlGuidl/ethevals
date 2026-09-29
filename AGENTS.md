# ETH Evals

This repo measures Ethereum knowledge with bare models and Ethereum work with agents.
The runner uses Inspect. Eval folders declare prompts, workspaces, and scorers.

## Read when needed

- Before writing project prose, read [CONTEXT.md](CONTEXT.md) for the vocabulary.
- Before adding or changing an eval, read [Add an eval](docs/add-an-eval.md).
- Before changing architecture or scoring contracts, read [the ADRs](docs/adr/) and [the runner reference](inspect-runner/README.md).
- Before changing CI or recovery, read [CI and publication](inspect-runner/README.md#ci-and-publication).
- Before changing the board, read [the site README](site/README.md).

## Run free checks

Use Python 3.13, uv, Node.js 22 or later, pnpm 9.14.2, and Docker with Compose.
Run these commands from the repository root in one shell:

```sh
unset OPENROUTER_API_KEY ANTHROPIC_API_KEY OPENAI_API_KEY ANTHROPIC_AUTH_TOKEN EXA_API_KEY
uv sync --frozen
(cd site && pnpm install --frozen-lockfile)
uv run ethevals validate
uv run pytest -q
(cd site && pnpm test)
```

Use the guide's `--evals` examples to check one folder.
To reproduce the full PR job, run:

```sh
docker ps
rm -rf results/ci
uv run python scripts/ci.py checks --output results/ci
```

On shared Docker, wait for other sessions' ETH Evals containers to finish before starting containers.
Give Docker at least 7 GiB for one stock act epoch. The default concurrency is one.

## Control spending and publication

Run paid epochs only with explicit spending intent and a reviewed budget.
`OPENROUTER_API_KEY` funds model calls. Optional `EXA_API_KEY` stays on the host.
The runner does not use `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, or `ANTHROPIC_AUTH_TOKEN` for model calls.
Inspect can read those variables, so keep all five unset for free work.
Before remote writes, read [CI and publication](inspect-runner/README.md#ci-and-publication).
Paid CI starts only after merge with a configured budget. Its default budget is zero.

Record architecture decisions as new ADRs in `docs/adr/` before changing scoring, result identity, or paid-run admission.
Keep ADR status honest. ADR 0002 remains proposed until its paid test passes.
Change `CONTEXT.md` only for an agreed vocabulary change.
List a new stock image input in `BUILD_INPUTS` in `inspect-runner/ethevals/images/tag.py`.
