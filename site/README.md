# ETH Evals board

The site builds a static board from the runner's catalog and results.
The browser receives public declarations and row details, without targets or scorer files.
[The root guide](../README.md#open-the-board) covers opening the board.

## Build

Use Node.js 22 or later, pnpm 9.14.2, and uv with Python 3.13.
From `site/`, run `pnpm install --frozen-lockfile`, then `pnpm build`.
The build writes `out/` for any static file host; no runtime server or database is required.
A normal build runs `ethevals catalog` to refresh `.catalog/catalog.json`.

## Demo data and settings

Run `ETHEVALS_DEMO=1 pnpm build` to use the invented board.
The banner labels demo results; log links open a bundled demo transcript.
Run `pnpm build` without that variable to return to real results.

All data paths resolve from `site/`.

| Setting | Default | Meaning |
| --- | --- | --- |
| `ETHEVALS_DEMO` | `0` | `1` selects `demo/catalog.json` and `demo/rows.jsonl`. |
| `ETHEVALS_ROWS` | `../results/rows.jsonl` | One runner results file. |

Demo mode and an explicit rows path cannot be combined.
A missing default rows file produces the empty state; a missing explicit file fails the build.
Malformed rows and duplicate epochs fail with their file and line.
The loader accepts schema version 5, skips older rows, and displays only current eval hashes.
The agent table switches between internet and skills rows.
The build reports loaded, current, and stale row counts.

Published rows supply full log URLs.
`ETHEVALS_LOGS_TOKEN` lets the build download missing release logs into `site/.logs/` for the bundled viewer.
The token needs read-only Contents access to `BuidlGuidl/ethevals`.
To download a run's logs from the repository root, run `gh release download <tag> --repo BuidlGuidl/ethevals --dir site/.logs`. The tag is in each row's `log_url`.
Build and dev bundle local `.eval` files into an Inspect viewer; matching board links open it and retain a download link.
`vercel.json` advertises byte-range support for bundled logs so Inspect can read their size when Vercel omits `Content-Length`.
See [the runner reference](../inspect-runner/README.md#ci-and-publication) for publication.

## Scores

An eval score is its share of passed epochs; errors remain visible but do not enter the denominator.
A pillar score averages eval scores, excluding evals without scored epochs.
The board shows epoch counts instead of confidence intervals.
Unsupported modes show `Not applicable`; supported cells without scores show `No epochs yet`.

Epoch cost adds model and grader cost. If either amount is unknown, the total stays unknown.
The panel shows the cost source, total tokens, and elapsed time from the row.
Different efforts stay in separate columns.
The loader computes cells once; the client reuses them for tables and the detail panel.

## Checks

From `site/`, run:

```sh
pnpm test
pnpm typecheck
pnpm lint
pnpm build
```

Tests include a key-free runner integration with fixture evals and no Docker.
After a demo build, `pnpm exec tsx scripts/check-export.ts demo` checks the exported assets.
After a build with no results, the same command with `empty` checks the empty board.
