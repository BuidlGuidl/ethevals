# Runner reference

The root `pyproject.toml` installs `ethevals` from this directory.
[The root guide](../README.md) covers installation.
[The Harbor guide](../docs/harbor.md) covers task files, verifiers, job settings, and results rows.

## Task folders

Write tasks directly in Harbor's format under `tasks/PILLAR/NAME/`.
Tasks belong to three pillars: Concepts, Build, and Act.
Concepts holds quizzes, Build holds builds, and Act holds tasks where the agent acts on a chain.
Each folder has `task.toml`, `instruction.md`, `environment/`, `tests/`, and `solution/`.
Copy a task with similar needs, then run the [free check](../docs/harbor.md#free-checks).

## Verifiers

Each task's `tests/test.sh` runs RewardKit, which writes the reward and named check details.
The [Harbor guide](../docs/harbor.md#free-checks) covers quiz targets, Forge, criteria, and sidecars.
A new test tool writes the same check records and ships in the task's environment image.
List shared image build inputs in [images/tag.py](ethevals/images/tag.py).

## Plan and run

Run paid trials only with explicit spending intent and a reviewed budget.
[Job settings](ethevals/job.yaml) select agents, models, CLI versions, and modes.
Use `--config` for a separate job configuration.
Use `--tasks`, `--agents`, `--models`, and `--modes` to select trials.
Use `--n-attempts N` for repeats or `--trial N` for one numbered trial.

```sh
uv run ethevals plan --modes internet --n-attempts 1 --budget 100
uv run ethevals run --modes internet --n-attempts 1 --budget 100 --output results/local
```

Every execution requires an explicit budget.
The reserve covers remaining API-key executions and paid criteria.
Plan-funded agents reserve no API spend, but their criteria still need a judge key and budget.
Read [Board jobs](../docs/harbor.md#board-jobs) for payment sources, recovery, and trajectory links.

Use `uv run harbor view results/local/jobs` to browse saved jobs locally.
The board opens published trials on Harbor Hub, with trajectory, verifier output, artifacts, and config.
Local runs publish publicly only with `ethevals run --upload-hub`.
Set the key variable named by `hub.key_env` in the job config before uploading.
The runner removes that key from the agent's execution environment and restores it for the upload.
Use `ethevals upload-hub --output results/local` to upload saved, checked jobs without running another trial.
Pass the same `--config` when the run used separate job settings.

## CI and publication

[checks.yml](../.github/workflows/checks.yml) runs free checks on pull requests without provider secrets.
It runs the [Harbor free check](../docs/harbor.md).
[results.yml](../.github/workflows/results.yml) queues paid trials after changes to `main`, except results-only changes.
It plans the internet and vanilla modes ([ADR 0019](../docs/adr/0019-two-trials-and-model-only-runs-in-ci.md)).
A manual budget overrides `ETHEVALS_BUDGET_USD`; the fallback is zero.
A zero budget saves the plan and schedules no trials, including plan-paid trials with no API reserve.
A positive budget must cover all missing trials' remaining API executions, including judge costs.

The workflow needs these GitHub secrets:

- `CLAUDE_CODE_OAUTH_TOKEN`: the Claude plan token. The job config forces plan payment and requires this token.
- `CODEX_AUTH_JSON`: the full ChatGPT `auth.json`. Rotate it weekly.
- `ANTHROPIC_API_KEY`: the judge and Anthropic vanilla trials.
- `OPENAI_API_KEY` and `OPENROUTER_API_KEY`: vanilla trials for those providers; OpenCode also uses OpenRouter.
  OpenCode runs as [`ethevals.opencode`](ethevals/opencode.py), whose `shell.env` plugin blanks its keys in the agent's shell commands.
- `EXA_API_KEY`, `MAINNET_RPC_URL`, and `BASE_RPC_URL`: optional search and task-declared fork credentials.
- `HARBOR_API_KEY`: Harbor Hub API key, available only to the upload step.

The job graph is `plan → matrix → publish`.
The plan reads current `main`; later jobs check out its saved SHA.
`scripts/ci.py plan-trials` folds current and pending results, saves the Harbor job config, and emits the admitted matrix.
CI schedules at most 256 trials, with at most 100 per plan group to fit GitHub's pending-job limit.
Later runs pick up deferred trials.
Plan groups use the configured agent name, so models and modes using the same plan share two lanes and run two trials at once.
Key-paid trials share 16 lanes. GitHub Free runs 20 jobs at once, so 4 runners stay free for the plan lanes and plan trials never wait behind key-paid ones.

`scripts/ci.py run-trial` executes one saved plan item with its reserved budget.
It checks task and skills hashes before Harbor starts.
Harbor builds each task's environment and starts its declared sidecars.
Codex credentials use a temporary file in a private directory outside the artifact directory; the step removes it afterward.
The file is readable by others, because Harbor copies it into the task as root and the agent user in most task images must read it.
Harbor receives `CODEX_AUTH_JSON_PATH` and uploads the file itself.
The job config forces Codex plan payment and requires plan tokens in its credential file before Harbor starts.
Local and CI trials use the same credential check.
The judge key enters only the verifier's commands; agent commands use their own configured credentials.
The run step allows 190 minutes; the job allows 240 minutes for setup, builds, and uploads too.
Each job uploads only `results/ci-run/public/` after success or failure.
Before the artifact upload, a separate step uploads checked Harbor jobs publicly to the configured Hub org.
That step checks its Hub key too and rebuilds the artifact if the check withholds a folder.
The default org is `buidlguidl`. Create its API key in Harbor Hub's profile settings.
The Hub key never reaches the step that runs the agent.
Successful uploads record links from Harbor's job and trial IDs in an artifact receipt.
Missing keys and failed uploads keep the trial result and schedule no extra paid trial.
The trajectory JSON remains a release asset and supplies the board link when the Hub upload fails or skips.
The trial step checks every file in each Harbor job folder while its credentials remain available.
Local runs use the same check before writing results rows.
The check matches exact credential values from job settings, including the judge key.
It also checks each task's declared host variables and the token values inside Codex `auth.json`.
The check ignores values shorter than eight bytes. Force flags such as `"1"` never match trial files.
A literal agent setting, such as a base URL, counts only when its name looks like a credential by Harbor's sensitive-key rule.
Checked folders carry a digest. Release staging refuses missing digests or files changed after the check.
Interrupted jobs keep private credential fingerprints. If their original credentials are unavailable, the check withholds their files.
Trials with a match keep an error row that names the variable and the files that held it, and omits its value.
Their raw files stay local and never enter the public artifact or release assets.
CI emits a warning and the trial reports an error.
Unreadable files and symlinks also withhold the job.
If the check withholds a trial, rotate the named credential.
Inspect its raw files on the machine that ran it. A CI runner is gone after the job, so the row's file names are what's left.
Keep those raw files private. Run a new trial with the replacement credential.
The planning step gets only RPC secrets; the trial step gets model credentials too.
Each secret has one declaration; YAML aliases share the RPC secrets between those steps.
Judge errors never schedule another agent execution automatically.
To repeat a judged trial, select one task, agent, mode, and trial number with `--retry-judge-error`.
This admits one execution, advances its retry number, and reserves its agent and judge costs under the budget.
It can repeat the agent's full work, including sidecar setup.
Keep the original rows and saved trial.
Use a fresh output directory.
Review the plan before running the same selection with the reviewed budget:

```sh
uv run ethevals plan --tasks TASK --agents AGENT --modes MODE --trial N --retry-judge-error --rows ROWS --budget USD --output results/recovery
uv run ethevals run --tasks TASK --agents AGENT --modes MODE --trial N --retry-judge-error --rows ROWS --budget USD --output results/recovery
```

Replace the uppercase values with the failed trial's selection, saved rows path, and reviewed budget.
The option also admits missing or broken reward output on a judged trial.
Malformed judge replies can cause this.
Other errors retain the configured retry policy.

The publisher has no model keys and runs after failed matrix jobs on `main`.
It downloads every workflow retry's artifacts and rebuilds rows from saved Harbor trials at their downloaded paths.
It folds retries before staging one trajectory JSON and one verifier archive per trial.
The archive includes check records and RewardKit's criterion reasons and usage.
Errors also keep their available output.

`publish-results` writes `combined/rows.jsonl`, `combined/release.json`, and `combined/assets/` locally.
Without `--publish`, it performs no remote writes.
With `--publish`, it records rows and release URLs on `ci/results` before uploading assets.
It folds `origin/main`, `origin/ci/results`, and artifact rows onto current `main`, without a force push.
The results pull request contains only the rows change.
The release uses the source commit and the workflow run ID; retries replace assets on that release.
If an upload fails, recorded rows keep the next plan from repeating completed trials.
Use "Re-run all jobs" to retry publication from every workflow retry.
A retry also reopens a missing results pull request without another push.

`ethevals publish-logs --output DIR --repo OWNER/REPO --run-id ID --commit SHA` stages a trial release locally.
Adding `--publish` uploads it through `gh` and saves a receipt under `DIR/published/`.

`ethevals export-hf --output DIR` copies every Harbor task folder to an empty directory.
It writes `registry.json`, Harbor metadata in `eval.yaml`, and the dataset card.
Task files remain unchanged. Published folders combine pillar and directory name under `tasks/`.
Registry entries use each task's `[task].name`.
`--hf-repo` and `--license` set dataset card values.
`scripts/ci.py release` previews the HF upload; `--publish` performs it.
The upload removes obsolete task files and the old quiz `data/` exports in the same HF commit.
[release.yml](../.github/workflows/release.yml) pushes shared images to GHCR before uploading every task to `buidlguidl/ethevals-test`.
It runs on pushes to `main`, except results-only changes, with `HF_TOKEN` and the workflow's GHCR token.
It tags dataset changes `gh-<short sha>` and supports manual reruns without inputs.
`scripts/ci.py images` builds shared images locally with the same pinned GHCR tags used by the source tasks.
Its `--publish` flag pushes Linux amd64 and arm64 images.
Pull-request, fork, and paid-trial jobs build locally, so they need no prior image release.
See [Dataset publication](../docs/harbor.md#dataset-publication) for standalone Harbor commands.

## Maintainer checks

Use Python 3.13, uv, Node.js 22 or later, pnpm 9.14.2, and Docker with Compose.
Keep all five provider key variables unset for free work.
From the repository root, run these commands in one shell:

```sh
unset OPENROUTER_API_KEY ANTHROPIC_API_KEY OPENAI_API_KEY ANTHROPIC_AUTH_TOKEN EXA_API_KEY
uv sync --frozen
(cd site && pnpm install --frozen-lockfile)
uv run ethevals lint
uv run pytest -q
(cd site && pnpm test && pnpm typecheck && pnpm lint && pnpm build)
```

On shared Docker, wait for other sessions' ETH Evals containers to finish before starting containers.
Run `docker ps` before starting containers.
Give Docker at least 7 GiB for one trial with a chain.
The default concurrency is one.

Run `uv run pytest -q --run-docker -m docker` for container checks.
Run `uv run python scripts/ci.py checks --output results/ci` for the full PR job.
Pull-request CI runs it as parallel parts: `--part unit`, `--part free`, and `--part docker --shard I/3`.
It skips the free and Docker parts when a pull request changes only `site/`, `docs/`, or top-level Markdown.
Use a fresh output directory.
