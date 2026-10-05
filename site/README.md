# ETH Evals board

The site builds a static board from the runner's catalog and results.
The browser receives public declarations and row details, without targets or scorer files.
[The root guide](../README.md#open-the-board) covers opening the board.

## Build

Use Node.js 22 or later, pnpm 9.14.2, and uv with Python 3.13.
From `site/`, run `pnpm install --frozen-lockfile`, then `pnpm build`.
The build writes `out/` for any static file host; no runtime server or database is required.
A normal build runs `ethevals catalog` to refresh `.catalog/catalog.json`.
The catalog has an `evals` list and one `skills_hash` for the current pack.

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
The loader accepts schema version 6 and skips older rows.
It displays only current eval hashes and, for skills-mode rows, the current skills hash.
A skills change reruns only skills-mode epochs and preserves internet and vanilla results.
The leaderboard switches between Internet, Internet + Skills, and Model only.
Internet and Internet + Skills share configuration rows; Model only shows bare models.
The eval matrix uses the same mode and groups evals under pillar bands.
The How it works page explains the pillars, modes, isolated runs, and publication pipeline.
The comparison page shows up to five configurations and highlights the best value for each metric.
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
Overall is the mean of scored pillar scores, excluding pillars without scores.
Skill lift averages the change over evals scored in both Internet and Internet + Skills for the same configuration.
Overall lift averages the pillar lifts, excluding pillars without paired evals.
Lift uses percentage points and stays unknown when no evals pair.
Each configuration includes its effort; different efforts stay separate.
`$ / pass` divides the model cost of scored epochs by passed epochs.
No passes or a missing model price produce `–`.
Cost limits count as failures. Errors remain in the drawer and do not enter scores or the cost calculation.

Epoch cost adds model and grader cost. If either amount is unknown, the total stays unknown.
The drawer shows the cost source, total tokens, elapsed time, checks, and error or limit from the row.
Its list and eval views use the `d` query parameter; browser Back closes a drawer opened from the board.
Runs expand inside the eval view, and the drawer keeps the mode selected when it opened.
Example links point to highlighted rows in the eval matrix.
Log links use the normal Inspect viewer when a matching log is bundled.
The loader computes cells, summaries, and lifts once; the client reuses them across pages.

## Interface

The site ports the geek design from Pablo's prototype to React components.
Tailwind CSS v4 defines its dark tokens and responsive layout in `app/globals.css`.
Styling uses named classes in `globals.css` built with `@apply`.
The used shadcn/ui components are Sheet, Tooltip, and ToggleGroup, built on Radix primitives.
JetBrains Mono covers the interface, VT323 covers section headings, and Archivo covers diagram text.
`next/font/google` bundles all three fonts during the build.
Motion animates the Results logo into the nav; reduced motion disables the animation.
Lucide supplies the stroke icons. The pipeline and isolated-run diagrams use inline SVG.
On phones, diagram notes form a vertical timeline and the detail drawer fills the screen.

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
