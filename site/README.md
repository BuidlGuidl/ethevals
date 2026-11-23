# ETH Evals board

The site builds a static board from Harbor task declarations and results rows.
It groups tasks into three pillars: Concepts, Build, and Act.
Concepts holds questions, Build holds builds, and Act holds tasks where the agent acts on a chain.
The browser receives public instructions and check records, without verifier files or targets.

## Build

Use Node.js 22 or later, pnpm 9.14.2, and uv with Python 3.13.
From `site/`, run `pnpm install --frozen-lockfile`, then `pnpm build`.
The build writes `out/` for a static file host.
It refreshes `.catalog/catalog.json` through `ethevals catalog`.
The catalog lists tasks and the current skills hash.

The Tasks page at `/evals/` shows catalog counts by domain, pillar, and area without results data.
Select a domain, pillar, and area to filter tasks. With Build selected, a layer filter appears too.
Share the URL to keep those filters. Domains without tasks have dashed borders and a coming soon tooltip.
The board's task matrix and trial drawer share the same `?domain=` filter as the Tasks page.
Use `dapp-development` or `security`; omit the parameter to show all tasks.
Click the selected domain again to clear it.
`src/areas.ts` maps areas to domains. Tasks without a mapped area belong to Dapp development, including demo tasks.
Expand a task to read its instruction and open its README on GitHub.

The share card is `public/og-image.png`, a 1200x630 screenshot of `scripts/share-card.html`. Render it again when the hero text changes.

The root layout loads Plausible for page analytics, with the `ethevals.com` script from the BuidlGuidl team.
It stays off in `pnpm dev` and on Vercel previews, and ignores visits from localhost.

Run `ETHEVALS_DEMO=1 pnpm build` for an invented board.
The banner labels its results, and its trajectory links are examples.
Demo mode and an explicit rows path cannot be combined.

`ETHEVALS_ROWS` selects a results file, relative to `site/`.
It defaults to `../results/rows.jsonl`.
A missing default file produces an empty board.
A missing explicit file fails the build.
Malformed rows and duplicate trials fail with their file and line.
The loader accepts schema version 8 and skips older rows.
The loader stamps rows without hashes from task history. It leaves the results file unchanged.
It requires current instruction and environment hashes and, for skills-mode rows, the current skills hash.
A row keeps its last result while its checks hash is behind.
It also drops trials numbered past the job's `n_attempts`.
It shows only models listed in the job settings.
The 160 Inspect rows have been removed.

## Scores and trajectories

The task matrix shows each configuration's task score.
Errors stay visible in the drawer and do not enter scores.
A pillar score averages its scored tasks.
Overall averages scored pillars.
The mode controls select Internet or Model only. Internet + Skills is marked coming soon.
Different agents, models, and efforts stay separate.
Compare shows Overall and pillar scores for up to five configurations.
Cost adds agent and judge API prices, even when a plan paid.

The scoring switch above the board defaults to All or nothing.
Select Gated or open `/?scoring=gated` to score the saved checks.
If any gate check fails, the trial score is 0%.
If every gate check passes, divide the checks passed by all counted checks.
The entry checks `compile`, `answered`, `no_answer`, and `report_written` are gate checks. Leave them out of the count.
`src/scoring-settings.ts` labels the other checks. An unlabeled check is a judgment check.
The leaderboard, task matrix, drawer, and Compare follow the scoring switch.

Under Gated every score is a percentage. A count such as "3 of 4 passed" sits next to a trial score and never replaces it.
The task list shows one dot per trial next to the task score: 100%, some checks missed, 0%, or error.
A trial at 0% says why: "Gate check failed", "No answer", "No report" or "Did not compile".
The trial drawer lists the entry check on its own line, then Gate checks and Judgment checks, each with a one-line note.
On audit tasks the second group is Known findings.
`pnpm exec tsx scripts/scoring-table.ts` prints Internet Overall and pillar scores under both rules.

Each trial drawer shows checks with reasons, cost, payment source, tokens, elapsed time, and errors.
No-answer trials say "Refused" or "Empty reply".
A trial that ended in an error says "Not scored" and that it is left out of the score. The runner's error text is not shown.
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
The separate `domain` parameter keeps the task filter when a drawer opens from the matrix.
The drawer's domain boxes show scores for its mode and pillar, and filter its task list.
Its main score stays across all domains. Tasks without scored trials show "–" with their trial status.
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
