# ETH Evals board

The agent table shows internet-mode results for each model and harness.
The knowledge table shows vanilla-mode results for bare models on quiz evals.
Expand a pillar to see its evals. Open a cell for its prompt, epochs, checks, and log links.

## Build the site

Use Node.js 22 or later, pnpm 9.14.2, and uv with Python 3.13.
From `site/`, run:

```sh
pnpm install --frozen-lockfile
pnpm build
```

The build writes `out/`, a static export with no runtime server or database.
It uses Next.js [static export](https://nextjs.org/docs/app/guides/static-exports).
Serve that folder through any static file host.

Without results, the page shows an empty state and the eval catalog.
A normal build never selects sample rows.

## See the sample board

From `site/`, run:

```sh
ETHEVALS_SAMPLE=1 pnpm build
python3 -m http.server 8000 --directory out
```

Open <http://localhost:8000>.
The banner labels all results as invented.
The sample covers every pillar, all cell states, a limit failure, and execution errors.
Its log links open a labelled sample transcript.

To return to real results, run `pnpm build` without `ETHEVALS_SAMPLE`.
If your shell exports that variable, unset it first.

## Data settings

The build runs `uv run ethevals catalog --output site/.catalog` from the repository root.
The runner loads the evals and exports their declarations and hashes to `site/.catalog/catalog.json`.
The site reads that catalog and one runner `rows.jsonl` file.
Sample builds use an invented `sample/catalog.json` fixture instead.
All paths below resolve from `site/`.

| Setting | Default | Meaning |
| --- | --- | --- |
| `ETHEVALS_SAMPLE` | `0` | `1` selects only `sample/rows.jsonl` and `sample/catalog.json`. |
| `ETHEVALS_ROWS` | `../results/rows.jsonl` | Path to one results file, with paths relative to its results folder. |
| `ETHEVALS_LOG_BASE` | Unset | URL of the published results folder, or an absolute site path. |

An absent default results file produces the empty state.
An absent explicit file fails the build. Sample mode and `ETHEVALS_ROWS` cannot be combined.
Malformed rows and duplicate epoch identities fail the build with the file and line.
This includes undeclared modes, mismatched pillars or types at the same hash, and invalid mode and harness pairs.
A missing evals root or catalog fails the build.
One build line reports the rows path and counts for shown, stale, key-free, and excluded skills rows.
An absent default file appears in that line.

For a published results folder, use:

```sh
ETHEVALS_ROWS=../results/paid/rows.jsonl \
ETHEVALS_LOG_BASE=https://example.org/ethevals/results \
pnpm build
```

A row with `log_file: logs/epoch.eval` links to `https://example.org/ethevals/results/logs/epoch.eval`.
The publisher must preserve the relative log paths under that base.
Without a base, the panel says that the full log is not published.
The site does not copy or publish real logs.

The loader accepts schema version 2.
The runner reads the real evals from `../evals/`. The site derives titles from their IDs.
It keeps prompts, choices, motivations, types, pillars, and declared modes.
The browser receives no scorer files or targets.

The runner supplies each hash. The site contains no eval hash algorithm or YAML declaration parser.
Only rows with the current eval hash enter the board.
Reference, empty, default mock, and other key-free rows never enter the board.
Internet results require a harness. Vanilla results require a bare model and a quiz eval.
Skills mode remains outside both tables.

## Scores and costs

An eval score is `passed / scored epochs`.
An epoch passes only when every named check passes.
Errors remain visible in the panel but do not enter the denominator.
Limits count as failed epochs because the runner records them as failed checks.

A pillar score is the mean of its eval scores.
Evals without scored epochs do not enter that mean.
The pillar's epoch count adds the eval counts together. It is not the denominator for the pillar mean.
The board shows counts instead of a confidence interval.

An unsupported mode shows `Not applicable`.
A pillar without evals that declare the mode shows `No evals yet` in both the table and panel.
A supported cell without scored epochs shows `No epochs yet`, with an error count when relevant.
Effort appears once in each subject's column header.
Different efforts stay separate because the runner treats them as distinct agent identities.

Epoch cost includes model cost and grader cost.
If either cost is unknown, the total stays unknown.
The panel retains both amounts and their sources, including guessed prices.
Total tokens include the model and grader. Time is the total elapsed time, including setup.

The loader groups rows by eval, mode, and subject once.
It computes each eval cell once and derives pillar means from those cells.
The client renders that model, so column highlights do not recalculate scores.
Epoch details contain only the fields the panel uses.

## Check the site

```sh
pnpm typecheck
pnpm lint
pnpm test
ETHEVALS_SAMPLE=1 pnpm build
pnpm exec tsx scripts/check-export.ts sample
pnpm build
pnpm exec tsx scripts/check-export.ts empty
```

The last check expects no paid rows at the default path.
The export checks inspect HTML and static assets without a browser or server.
Tests assert literal score inputs and outputs, including missing epochs, errors, and key-free rows.

## Design

The page keeps prototype view 4's dark palette, system type, score thresholds, and column hover highlight.
Red means below 25%, amber means below 50%, and green means 50% or more.
These colors describe pass rates. They do not set a safety threshold for using an agent.

The two tables share one page. The internet label reserves space for a future skills toggle.
The detail panel uses a native modal dialog, Escape to close, and focus return to the opening cell.
Tables scroll horizontally on narrow screens and retain the row labels.
Keyboard focus highlights the same column as pointer hover.
No component library, remote fonts, or charting package is required.

Browser and visual checks remain with Shiv, as requested in the brief.
