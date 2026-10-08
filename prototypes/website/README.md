# Website prototype

A design proposal for the ETH Evals website, built on the board layout chosen in PR #2 (view 4, skills toggle).
It runs on invented data, so it can show a fuller board than the current real runs.

Open `index.html` directly in a browser. No server or install is needed.

## Pages

- **Results** (`#/`): the four pillars, the leaderboard with Internet, Internet + Skills and Model only, and every score broken down by eval. Click a score for its evals, runs and checks.
- **Compare** (`#/compare`): up to five configurations side by side.
- **How it works** (`#/how`): the pipeline from pull request to board, the three eval types, what the system runs on, and the rules every run follows.
- Eval pages (`#/eval/<id>`) and run pages (`#/run/<id>`), reached from the results.

## Files

| File | Role |
| --- | --- |
| `site-simple.js`, `site-simple.css` | Results, Compare, eval and run pages, routing |
| `how-it-works.js`, `how-it-works.css` | The How it works page and its diagrams |
| `data.js`, `data-extra.js` | Invented evals, agents and runs |
| `style.css`, `report.css`, `report-lab.css`, `site.css` | Shared base styles from the earlier prototype views |

## Next step

Once the design is agreed, port it to the real board in `site/`, where it reads `results/rows.jsonl`.
The idea is one site with two datasets: real results at `/` and this kind of richer sample data at `/demo`.
