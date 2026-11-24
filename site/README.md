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
The catalog lists tasks, their check tags, and the current skills hash.

The Tasks page at `/evals/` shows catalog counts by domain, pillar, and area without results data.
Select a domain, pillar, and area to filter tasks. With Build selected, a layer filter appears too.
Copy the URL to keep those filters. Domains without tasks have dashed borders and a coming soon tooltip.
The board's task matrix and trial drawer use the same `?domain=` filter as the Tasks page.
Use `dapp-development` or `security`; omit the parameter to show all tasks.
Click the selected domain again to clear it.
`src/areas.ts` maps areas to domains. Tasks without a mapped area belong to Dapp development, including demo tasks.
Expand a task to read its instruction and open its README on GitHub.

The social preview image is `public/og-image.png`, a 1200x630 screenshot of `scripts/share-card.html`. Render it again when the hero text changes.

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
If a Build or Act row has the current checks hash, every non-entry check in the row needs a tag.
A missing tag fails the build with the task, check name, and row location.
It also drops trials numbered past the job's `n_attempts`.
It shows only models listed in the job settings.
The 160 Inspect rows have been removed.

## Scores and trajectories

The leaderboard, Compare, and the task matrix show percentages.
A failed gate check or entry check sets the trial score to 0%.
Otherwise, the trial score divides the checks passed by the gate and judgment checks in the row.
Concepts trials count their answer check and score 100% or 0%.
The entry checks are `compile`, `answered`, `no_answer`, and `report_written`. They stay out of the count.
On an older row, ignore checks without a current tag and tags for checks the row lacks.
If no checks count and no entry check failed, the saved trial status gives 100% for a pass and 0% for a fail.
A task score averages its trial scores. Errors stay visible in the drawer and stay out of the average.
A pillar score averages its task scores. Overall averages its pillar scores.
The task matrix tooltip lists the trials behind each task score.
Tile color shows how far a score is from the best score in its leaderboard column or task row. Leaderboard and drawer leaders use a mint numeral, and a 0% score is never shown as best.
A score with planned trials that have no score yet shows an amber info icon in its corner.
The icon's tooltip gives the count, such as "18 trials have no score yet."
It counts errors and trials that have not run, up to the job's `n_attempts` for each task in the selected mode.
Overall, pillar scores, and task matrix cells carry it. A task without scored trials keeps its "–".
The drawer shows the same sentence in an amber banner under the configuration, for the scores or the task it shows.
The mode controls select Internet or Model only. Internet + Skills is marked coming soon.
Different agents, models, and efforts stay separate.
Compare shows Overall and pillar scores for up to five configurations.
Cost adds agent and judge API prices, even when a plan paid.

The drawer task list shows one dot per trial for 100%, some checks missed, 0%, or error.
The trials table shows the trial score, followed by the check count or the reason a gate check or entry check stopped the trial score at 0%.
The trial view groups Gate checks and Judgment checks under headings with counts and info notes. Concepts has one Checks group.
Each group lists failed checks first, then passed checks, each with its reason.
A failed entry check appears above the groups. Passed entry checks stay out of the view.
The trial view also shows cost, payment source, tokens, and elapsed time.
An errored trial says "Not scored" and explains why it stays out of the score.
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
Run `pnpm exec tsx scripts/scoring-table.ts` to print Internet Overall and pillar scores after a build generates the catalog.

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
