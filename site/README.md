# ETH Evals board

The site builds a static board from Harbor task declarations and results rows.
It groups tasks into three pillars: Concepts, Build, and Act.
Concepts holds quizzes, Build holds builds, and Act holds tasks where the agent acts on a chain.
The browser receives public instructions and check records, without verifier files or targets.

## Build

Use Node.js 22 or later, pnpm 9.14.2, and uv with Python 3.13.
From `site/`, run `pnpm install --frozen-lockfile`, then `pnpm build`.
The build writes `out/` for a static file host.
It refreshes `.catalog/catalog.json` through `ethevals catalog`.
The catalog lists tasks and the current skills hash.

Run `ETHEVALS_DEMO=1 pnpm build` for an invented board.
The banner labels its results, and its trajectory links are examples.
Demo mode and an explicit rows path cannot be combined.

`ETHEVALS_ROWS` selects a results file, relative to `site/`.
It defaults to `../results/rows.jsonl`.
A missing default file produces an empty board.
A missing explicit file fails the build.
Malformed rows and duplicate trials fail with their file and line.
The loader accepts schema version 8 and skips older rows.
It shows only current task hashes and, for skills-mode rows, the current skills hash.
The 160 Inspect rows have been removed.

## Scores and trajectories

The task matrix shows passed trials out of scored trials.
Errors stay visible in the drawer and do not enter scores.
A pillar score averages its task pass rates.
Overall averages scored pillars.
The mode controls select Internet, Internet + Skills, or Model only.
Different agents, models, and efforts stay separate.
`$ / pass` divides model cost for scored trials by passed trials.
No passes or unknown cost produce `–`.
Cost adds agent and judge API prices, even when a plan paid.

Each trial drawer shows checks with reasons, cost, payment source, tokens, elapsed time, and errors.
Its trajectory link opens the row's `trajectory_url`.
Harbor Hub links say "Open full trial on Harbor Hub" and open the public trial page.
If the Hub upload fails or skips, published rows link to the release's trajectory JSON.
Published rows use a full HTTP URL.
Local rows use `/trajectories/<id>.json` and a `trajectory_file` path.
The build copies that file into the static export.
Relative file paths resolve from the rows file's directory.
A local link without a file fails the build.
The browser never receives host paths.
No Inspect viewer or log download runs during the build.

The drawer's `d` query parameter keeps its task, mode, configuration, and trial selection.
Browser Back closes a drawer opened from the board.
The loader computes cells and summaries once for all pages.

## Checks

From `site/`, run:

```sh
pnpm test
pnpm typecheck
pnpm lint
pnpm build
```

The runner integration reads a recorded real Harbor oracle trial without Docker or provider keys.
After a demo build, run `pnpm exec tsx scripts/check-export.ts demo`.
After a build with no results, use `empty` instead.
