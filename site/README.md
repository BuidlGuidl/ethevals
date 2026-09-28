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
| `ETHEVALS_ROWS` | `../results/rows.jsonl` | Path to one results file. Published rows contain release-relative log paths. |
| `ETHEVALS_LOG_BASE` | Unset | GitHub release-download base URL, or an absolute site path. |

An absent default results file produces the empty state.
An absent explicit file fails the build. Sample mode and `ETHEVALS_ROWS` cannot be combined.
Malformed rows and duplicate epoch identities fail the build with the file and line.
This includes undeclared modes, mismatched pillars or types at the same hash, and invalid mode and harness pairs.
A missing evals root or catalog fails the build.
One build line reports the rows path and counts for shown, stale, key-free, and excluded skills rows.
An absent default file appears in that line.

After publishing logs with `ethevals publish-logs --publish`, use:

```sh
ETHEVALS_ROWS=../results/paid/published/results-12345-1.jsonl \
ETHEVALS_LOG_BASE=https://github.com/BuidlGuidl/ethevals/releases/download \
pnpm build
```

A row with `log_file: results-12345-1/epoch.eval` links to
`https://github.com/BuidlGuidl/ethevals/releases/download/results-12345-1/epoch.eval`.
Rows from other runs carry other release tags, so one base reaches all releases.
CI records attempts in `results/rows.jsonl` and artifact receipts in `results/runs.json` before it uploads logs.
It adds release links afterward. Failed publication leaves scores and attempt counts intact.
The publisher rebuilds rows from the run artifact's logs, including interrupted attempts.
An unrecorded earlier artifact blocks paid CI work. Retry its publication job before the 14-day artifact expires.
The root README gives the local recovery command.
Receipt and release identities come from the artifact's executing run and attempt, even after a publish-only retry.
Only runs that began paid work need receipts. Gated and zero-work runs open no results PR.
Recovery scans the 14-day artifact window in a separate step with its own read token.
The root README documents `scripts/ci.py accept-loss` for artifacts that cannot be recovered.
That receipt accepts lost spend. Missing rows can cause future runs to pay for those epochs again.
Execution errors remain visible without log links. Their unpublished logs stay in the workflow artifact.
The publisher writes linked rows after the upload succeeds, in a file named for the release.
Its dry run writes nothing. It excludes key-free, stale-hash, skills, and already published logs.
Only `results-<run-id>/<asset>.eval` paths receive release links when `ETHEVALS_LOG_BASE` is set.
Local `logs/` paths remain visible without links. Sample mode keeps its bundled log links.
The row fold preserves newer attempts regardless of publication order.
The site still reads one rows file and rejects duplicate identities.
The link downloads the `.eval` file. Open its local folder with `inspect view --log-dir path/to/folder`.
Private repository assets require GitHub access. Public downloads require a public repository.
Without a base, the panel says that the full log is not published.
The site does not copy or publish real logs.

The loader accepts schema version 3 only. Version 2 rows fail with the file and line.
Metered costs, execution attempts, and version metadata do not enter the board's display model.
The runner reads the real evals from `../evals/`. The site derives titles from their IDs.
It keeps prompts, choices, motivations, types, pillars, and declared modes.
The browser receives no scorer files or targets.

The runner supplies each hash from the same captured file manifest that supplies execution inputs.
The site contains no eval hash algorithm or YAML declaration parser.
Only rows with the current eval hash enter the board.
Reference, empty, default mock, and other key-free rows never enter the board.
Key-free internet build rows can have no harness. The loader accepts and excludes them.
Displayed internet results require a harness. Vanilla results require a bare model and a quiz eval.
Skills mode remains outside both tables.

## Scores and costs

An eval score is `passed / scored epochs`.
An epoch passes only when every named check passes.
Errors remain visible in the panel but do not enter the denominator.
Limits count as failed epochs because the runner records them as failed checks.
Invalid Solidity bytes, confirmed scorer OOM kills, and empty grader reasons also produce failed checks.
Docker exec failures, capture timeouts, and grader transport failures remain errors.
The runner's `run()` function requires a budget for paid work. CI calls that same entry point.
Exa search runs on the host through a tool bridge. Its optional key never enters containers or logs.
The plan reserves the configured search price for each allowed request and also bounds selected epochs by wall time.
The bridge offers `web_search_exa` and `web_fetch_exa` with Exa's hosted descriptions and schemas.
Both share the 20-request epoch cap. `search_capped` counts our refusals, while `search_rate_limited` counts Exa throttling.
Keyed search remains unverified until the first keyed run.

The private CI runner has 2 CPUs, 8 GB of RAM, and 14 GB of disk.
Each container has a 1 GiB limit, with at most three containers per epoch and two concurrent epochs.
Local concurrency also must fit Docker's memory capacity, with at least 1 GiB left for the host.
Admission uses the list-scheduling bound after it deducts measured preparation and discovery time.
Sandbox epochs include 600 seconds for startup and 60 for cleanup. Act setup adds another 150 seconds.
Task initialization and final task cleanup each have a 60-second deadline. The plan reserves both outside the parallel bound.
The standalone CI plan admits 7 of 72 epochs before preparation time is known. The run saves its final count afterward.
Admission interleaves models. The execution step stops after 310 minutes within the 330-minute job.

Author script crashes and malformed replies are the one deliberate fail-closed exception: they produce failed checks.
Missing scripts, wrapper failures, host timeouts, and host kills remain errors.
The [classification table](../README.md#failure-classification) gives the full rule.
The panel uses the row's `limit` field to identify limits and displays the runner's check reasons.

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
Search charges enter the run plan's reserve but have no metered cost in the rows.
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
The runner integration test requires uv and Python. It creates a catalog and runs one key-free quiz check without Docker.

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
