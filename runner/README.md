# Runner reference

The root `pyproject.toml` installs `ethevals` from this directory.
[The root guide](../README.md) covers installation.
[The Harbor guide](../docs/harbor.md) covers task files, verifiers, job settings, and results rows.

## Task folders

Write tasks directly in Harbor's format under `tasks/PILLAR/NAME/`.
Each folder has `task.toml`, `instruction.md`, `environment/`, `tests/`, and `solution/`.
Copy a task with similar needs, then run the [free check](../docs/harbor.md#free-checks).

## Verifiers

Each task's `tests/test.sh` writes named checks and an all-checks reward.
The [Harbor guide](../docs/harbor.md#free-checks) covers quiz targets, Forge, criteria, and sidecars.
A new test tool writes the same check records and ships in the task's environment image.
List shared image build inputs in [images/tag.py](ethevals/images/tag.py).

## Plan and run

[Job settings](ethevals/job.yaml) select agents, models, CLI versions, modes, and the time limit.
Use `--config` for a separate job configuration.
Use `--tasks`, `--agents`, `--models`, and `--modes` to select trials.
Use `--trials N` for repeats or `--trial N` for one numbered trial.

```sh
uv run ethevals plan --modes internet --trials 1 --budget 100
uv run ethevals run --modes internet --trials 1 --budget 100 --output results/local
```

Every execution requires an explicit budget.
The reserve covers remaining API-key attempts and paid criteria.
Plan-funded agents reserve no API spend, but their criteria still need a judge key and budget.
Read [Board jobs](../docs/harbor.md#board-jobs) for payment sources, recovery, and trajectory links.

## CI and publication

[checks.yml](../.github/workflows/checks.yml) runs free checks on pull requests without provider secrets.
It runs the [Harbor free check](../docs/harbor.md).
[results.yml](../.github/workflows/results.yml) queues paid trials after changes to `main`, except results-only changes.
A manual budget overrides `ETHEVALS_BUDGET_USD`; the fallback is zero.
A zero budget saves the plan and schedules no trials, including plan-paid trials with no API reserve.
A positive budget must cover all missing trials' remaining API attempts, including judge costs.

The workflow needs these GitHub secrets:

- `CLAUDE_CODE_OAUTH_TOKEN`: the Claude plan token. `CLAUDE_FORCE_OAUTH=1` keeps the API key out of Claude Code.
- `CODEX_AUTH_JSON`: the full ChatGPT `auth.json`. Rotate it weekly.
- `ANTHROPIC_API_KEY`: the judge and Anthropic vanilla trials.
- `OPENAI_API_KEY` and `OPENROUTER_API_KEY`: vanilla trials for those providers; OpenCode also uses OpenRouter.
- `EXA_API_KEY`, `MAINNET_RPC_URL`, and `BASE_RPC_URL`: optional search and task-declared fork credentials.

The job graph is `plan → matrix → publish`.
The plan reads current `main`; later jobs check out its saved SHA.
`scripts/ci.py plan-trials` folds current and pending results, saves the Harbor job config, and emits the admitted matrix.
CI schedules at most 256 trials, with at most 100 per plan group to fit GitHub's pending-job limit.
Later runs pick up deferred trials.
Plan groups use the configured agent name, so models and modes using the same plan share one queue.
Key-paid trials have separate groups and can run in parallel.

`scripts/ci.py run-trial` selects one saved trial and calls the Harbor CLI path with its reserved budget.
Harbor builds each task's environment and starts its declared sidecars.
Codex credentials use a temporary mode-0600 file outside the artifact directory; the step removes it afterward.
Harbor receives `CODEX_AUTH_JSON_PATH` and uploads the file itself.
`CODEX_FORCE_AUTH_JSON=1` prevents an absent plan secret from falling back to the OpenAI key.
The judge key stays on the host while Claude Code uses its plan token.
The run step allows 190 minutes; the job allows 240 minutes for setup, builds, and uploads too.
Each job uploads saved trials after success or failure.

The publisher has no model keys and runs after failed matrix jobs on `main`.
It downloads every attempt's artifacts and rebuilds rows from saved Harbor trials at their downloaded paths.
It folds attempts before staging one trajectory JSON and one verifier archive per trial.
The archive includes check records, reasons, and any `judge.json`.
Errors also keep their available output.

`publish-results` writes `combined/rows.jsonl`, `combined/release.json`, and `combined/assets/` locally.
Without `--publish`, it performs no remote writes.
With `--publish`, it records rows and release URLs on `ci/results` before uploading assets.
It folds `origin/main`, `origin/ci/results`, and artifact rows onto current `main`, without a force push.
The results pull request contains only the rows change.
The release uses the source commit and the workflow run ID; retries replace assets on that release.
If an upload fails, recorded rows keep the next plan from repeating completed trials.
Use "Re-run all jobs" to retry publication from every workflow attempt.
A retry also reopens a missing results pull request without another push.

`ethevals publish-logs --output DIR --repo OWNER/REPO --run-id ID --commit SHA` stages a trial release locally.
Adding `--publish` uploads it through `gh` and saves a receipt under `DIR/published/`.

`ethevals export-hf --output DIR` copies every Harbor task folder to an empty directory.
It writes `registry.json`, Harbor metadata in `eval.yaml`, and the dataset card.
Task files remain unchanged. Published names combine pillar and task name under `tasks/`.
`--hf-repo` and `--license` set dataset card values.
`scripts/ci.py release` previews the HF upload; `--publish` performs it.
The upload removes obsolete task files and the old quiz `data/` exports in the same HF commit.
[release.yml](../.github/workflows/release.yml) pushes shared images to GHCR before uploading every task to `buidlguidl/ethevals-test`.
It runs on pushes to `main` with `HF_TOKEN` and the workflow's GHCR token.
It tags dataset changes `gh-<short sha>` and supports manual reruns without inputs.
`scripts/ci.py images` builds shared images locally with the same pinned GHCR tags used by the source tasks.
Its `--publish` flag pushes Linux amd64 and arm64 images.
Pull-request, fork, and paid-trial jobs build locally, so they need no prior image release.
See [Dataset publication](../docs/harbor.md#dataset-publication) for standalone Harbor commands.

## Maintainer checks

Unset provider keys before free work.
Run `uv run pytest -q` for unit tests.
Run `uv run pytest -q --run-docker -m docker` for container checks.
Run `uv run python scripts/ci.py checks --output results/ci` for the full PR job.
Use a fresh output directory.
