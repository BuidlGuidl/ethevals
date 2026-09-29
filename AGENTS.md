# ETH Evals

This repo measures Ethereum knowledge with bare models and Ethereum work with agents.
The runner uses Inspect. Eval folders declare prompts, workspaces, and scorers.

## Read when needed

- Before writing project prose, read [CONTEXT.md](CONTEXT.md) for the vocabulary.
- Before adding or changing an eval, read [Add an eval](docs/add-an-eval.md).
- Before changing architecture or scoring contracts, read [the ADRs](docs/adr/) and [the runner reference](inspect-runner/README.md).
- Before changing CI or recovery, read [CI and committed results](README.md#ci-and-committed-results).
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
uv run python scripts/ci.py checks --output results/author-guide-ci
```

On shared Docker, wait for other sessions' ETH Evals containers to finish before starting containers.
Use a fresh output folder for the full job.
Docker needs the sum of service memory limits per concurrent epoch plus 1 GiB for the host.
One stock act epoch needs 6.25 GiB in total. The default concurrency is one.

`check` makes no paid calls and skips rubrics.
Require passing references and failing untouched cases, with no execution errors.
Read each check's reason. Quiz references do not prove the prompt's facts.
Results rows use `status`, and each named check has `passed` and `reason`.
Keep exact catalog and export assertions current when adding evals. The guide names the affected tests.

## Keep evals within the author contract

Select grading through `scorer/target.yaml`, `scorer/tests/`, `scorer/rubric.md`, or a check script.
Put reference files under `scorer/solution/`. They overlay the workspace before an optional `run.sh` runs.
For act scripts, prefer Bash with `cast` or `forge`. Use Python when it improves readability.
Setup and check files use `setup` or `check`, with an optional extension and an interpreter shebang.
Return named verdicts for unwanted chain states. Script crashes and malformed output are errors.
Keep private expected state out of setup output and reachable services.
The runner isolates scorer files locally, but the repository publishes them and scoring has internet access.
Do not rely on scorer secrecy.

Do not add `workspace/foundry.toml`. The runner owns grading settings and installed libraries.
An eval's `compose.yaml` contains only extra services and named volumes.
Pin extra-service images by digest, set positive memory limits, and join only the private network.
Keep generated logs and mock rows out of committed `results/rows.jsonl`.

## Control spending and publication

Run paid epochs only with explicit spending intent and a reviewed budget.
`OPENROUTER_API_KEY` funds model calls. Optional `EXA_API_KEY` stays on the host.
The runner does not use `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, or `ANTHROPIC_AUTH_TOKEN` for model calls.
Inspect can read those variables, so keep all five unset for free work.
Before remote writes, read [CI and committed results](README.md#ci-and-committed-results) and [Publish full logs](README.md#publish-full-logs).
Paid CI starts only after merge with a configured budget. Its default budget is zero.

Record architecture decisions as new ADRs in `docs/adr/` before changing scoring, result identity, or paid-run admission.
Keep ADR status honest. ADR 0002 remains proposed until its paid test passes.
Change `CONTEXT.md` only for an agreed vocabulary change.
If changing image inputs, follow the README's image-tag procedure. Tags identify inputs, not image bytes.
