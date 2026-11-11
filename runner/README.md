# Runner reference

The root `pyproject.toml` installs `ethevals` from this directory.
[The root guide](../README.md) covers installation.
[The Harbor guide](../docs/harbor.md) covers task files, verifiers, job settings, and results rows.

## Task folders

Write tasks directly in Harbor's format under `tasks/PILLAR/NAME/`.
Tasks belong to three pillars: Concepts, Build, and Act.
Concepts holds questions, Build holds builds, and Act holds tasks where the agent acts on a chain.
Each folder has `task.toml`, `instruction.md`, `environment/`, `tests/`, and `solution/`.
Copy a task with similar needs, then run the [free check](../docs/harbor.md#free-checks).

## Verifiers

Each task's `tests/test.sh` runs RewardKit, which writes the reward and named check details.
The [Harbor guide](../docs/harbor.md#free-checks) covers Concepts task targets, Forge, criteria, and sidecars.
A new test tool writes the same check records and ships in the task's environment image.
List shared image build inputs in [images/tag.py](ethevals/images/tag.py).

Judges use RewardKit's `claude-code` agent on Opus 5.5 at high effort, with `guard = "flag"`.
`CLAUDE_CODE_OAUTH_TOKEN` pays through the Claude plan. Results retain the API-price cost.
File-reading judges receive saved inputs inside their working directory.
Browser judges get source, the built page, a wallet, chain reads, and task fixture commands.
The judge starts one folder above submitted code with fresh user settings.
Build commands and submitted child processes receive no judge token.
A judge crash or timeout removes the reward and records a trial error.
Shared verifiers retain the container isolation gap in [ADR 0011](../docs/adr/0011-verifiers-use-rewardkit-and-criteria-run-in-the-task.md).

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
Plan-paid agents and judges reserve no API spend. Both still require an explicit execution budget.
Read [Board jobs](../docs/harbor.md#board-jobs) for payment sources, recovery, and trajectory links.

Use `uv run harbor view results/local/jobs` to browse saved jobs locally.
The board opens published trials on Harbor Hub, with trajectory, verifier output, artifacts, and config.
Local runs publish publicly only with `ethevals run --upload-hub`.
Set the key variable named by `hub.key_env` in the job config before uploading.
The runner removes that key from the agent's execution environment and restores it for the upload.
Use `ethevals upload-hub --output results/local` to upload saved, checked jobs without running another trial.
Pass the same `--config` when the run used separate job settings.

## Identity and no answer

A trial's identity includes its task ID, instruction hash, environment hash, agent, model, effort, mode, and trial number.
Skills-mode identities also include the skills hash.
A row keeps Harbor's whole-folder `task_hash` and the `checks_hash` that decided its checks.
Rows keep schema version 8. The hash fields mark stamped rows.

`instruction.md` supplies the instruction hash.
Environment files and agent settings supply the environment hash.
Tests, criteria, verifier settings, artifact declarations, and the job's judge program, model, and effort supply the checks hash.
The task README, solutions, descriptions, authors, keywords, and task versions change no trial identity or checks hash.
Known display fields and mode declarations also stay outside the hashes.
Unknown files and settings count as environment inputs.
A changed instruction or environment hash reruns every selected mode.
A changed checks hash plans a regrade, or a rerun when the saved work cannot support the changed checks.
The board requires current instruction and environment hashes, plus the skills hash in skills mode.
It keeps the saved result while its checks hash is behind.

`uv run ethevals stamp-rows --rows results/rows.jsonl` stamps saved rows without hashes.
It finds task files whose Harbor digest matches each row, including historical files in Git.
It preserves each row's status and fields, and adds the hashes.
It leaves stamped rows unchanged on repeat runs.
If a matching folder is unavailable, it stops before writing rows.

A refusal, or an empty final reply to a Concepts task, counts as no answer.
A reply with words goes to the checks.
No answer gets one immediate retry in the same CI job, for agents and bare models.
The retry adds no scored trial, consumes no normal retry, and reserves no extra budget.
Two no-answer tries count as a fail.
One saved no-answer try without a completed second try counts as an error under the normal retry rule.
The row retains the no-answer history and stop reasons, even when the second try answers.
The bare-model runner also saves the provider stop reason beside its trajectory.

## Regrade saved work

The planner lists regrades under `regrades` and agent trials under `missing`.
Concepts regrades run the task's real tests through RewardKit in its verifier image.
Rows for one task share a container.
Unchanged judge criteria and inputs keep their saved results.
A criteria change, judge program, model, or effort change, or changed file input asks the judge again.
A judge that declares MCP servers needs a live session. A judge-only change reruns those trials.
Judge-only regrades reuse saved inputs and keep the other checks.
Contract Build tasks with separate verifiers and no sidecars use Harbor's `trial regrade` on saved trial files.
Checks that need a live browser or chain plan reruns.
Saved work with no address, an HTTP 404 or 410, or expired CI artifacts plans a rerun.
The plan lists each rerun and its reason.
Other fetch errors defer the regrade until the next CI run and reserve nothing.
A failed regrade leaves the saved row unchanged and fails its CI job.

To inspect a check fix locally, run:

```sh
uv run ethevals regrade --tasks tasks/concepts/compiler-legacy-init-order --modes internet vanilla --budget 0 --output results/check-fix
```

The command writes new rows and prints status changes after successful regrades.
It skips missing agent trials.
A regrade preserves the original trajectory link and model cost, and replaces the checks and verifier output.
A regrade without a judge reserves zero.
A plan-paid judge regrade reserves no API spend. API-paid judges keep the same budget rule as trials.
Paid judge calls still require explicit spending intent and a reviewed budget.

## CI and publication

[checks.yml](../.github/workflows/checks.yml) runs free checks on pull requests without provider secrets.
It runs the [Harbor free check](../docs/harbor.md).
[results.yml](../.github/workflows/results.yml) queues paid trials after changes to `main`, except results-only changes.
It plans the internet and vanilla modes ([ADR 0020](../docs/adr/0020-two-trials-and-model-only-runs-in-ci.md)).
A manual budget overrides `ETHEVALS_BUDGET_USD`; the fallback is zero.
A zero budget saves the plan and schedules no jobs, including free regrades and plan-paid trials.
A positive budget must cover all missing trials' remaining API executions and all planned judge regrades.

The workflow needs these GitHub secrets:

- `CLAUDE_CODE_OAUTH_TOKEN`: the Claude plan token. The job config forces plan payment and requires this token.
- `CODEX_AUTH_JSON`: the full ChatGPT `auth.json`. Rotate it weekly.
- `ANTHROPIC_API_KEY`: Anthropic vanilla trials.
- `OPENAI_API_KEY` and `OPENROUTER_API_KEY`: vanilla trials for those providers; OpenCode also uses OpenRouter.
  OpenCode runs as [`ethevals.opencode`](ethevals/opencode.py), whose `shell.env` plugin blanks its keys in the agent's shell commands.
- `EXA_API_KEY`, `MAINNET_RPC_URL`, and `BASE_RPC_URL`: optional search and task-declared fork credentials.
- `HARBOR_API_KEY`: Harbor Hub API key, available only to the upload step.

The job graph is `plan → matrix and regrade → publish`.
The plan reads current `main`; later jobs check out its saved SHA.
Each trial or regrade CI job downloads the exact plan artifact named by its plan job's output.
Resuming only failed jobs keeps that output.
If the plan job runs again, it saves a new artifact for the workflow attempt.
If that exact artifact is missing or expired, the download fails without using another plan.
This applies to workflows started after the change lands.
Old runs keep their original workflow definition when rerun, because [GitHub retains the original commit](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/re-run-workflows-and-jobs).
`scripts/ci.py plan-trials` folds current and pending results, saves the Harbor job config, and emits the admitted matrix.
CI schedules at most 256 jobs, with at most 100 per plan group to fit GitHub's pending-job limit.
Regrade jobs group rows by task and receive only the judge credential when they need it.
The plan also limits each release to 1,000 assets and defers work beyond that limit.
The plan lists regrade batches deferred by job or asset limits.
Later runs pick up deferred trials and regrades.
Plan groups use the configured agent name, so models and modes using the same plan share five lanes and run five trials at once.
Key-paid trials share 10 lanes. GitHub Free runs 20 jobs at once, so 10 runners stay free for the plan lanes and plan trials never wait behind key-paid ones.
One job runs all of a model's vanilla trials, since each is one API call and shorter than the job's setup.

`scripts/ci.py run-trial` executes one saved plan item with its reserved budget.
It checks task, instruction, environment, checks, and skills hashes before Harbor starts.
Harbor builds each task's environment and starts its declared sidecars.
Codex credentials use a temporary file in a private directory outside the artifact directory; the step removes it afterward.
The file is readable by others, because Harbor copies it into the task as root and the agent user in most task images must read it.
Harbor receives `CODEX_AUTH_JSON_PATH` and uploads the file itself.
The job config forces Codex plan payment and requires plan tokens in its credential file before Harbor starts.
Local and CI trials use the same credential check.
The judge plan token enters only the verifier's commands; agent commands use their own configured credentials.
The run step allows 190 minutes; the job allows 240 minutes for setup, builds, and uploads too.
Each trial or regrade job uploads only `results/ci-run/public/` after success or failure.
CI artifacts remain available for 14 days.
Before the artifact upload, a separate step uploads checked Harbor jobs publicly to the configured Hub org.
That step checks its Hub key too and rebuilds the artifact if the check withholds a folder.
The default org is `buidlguidl`. Create its API key in Harbor Hub's profile settings.
The Hub key never reaches the step that runs the agent.
Successful uploads record links from Harbor's job and trial IDs in an artifact receipt.
Missing keys and failed uploads keep the trial result and schedule no extra paid trial.
The trajectory JSON remains a release asset and supplies the board link when the Hub upload fails or skips.
The trial step checks every file in each Harbor job folder while its credentials remain available.
Local runs use the same check before writing results rows.
The check matches exact credential values from job settings, including the judge plan token.
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
It folds retries before staging each trial's trajectory JSON and verifier archive.
Regrades retain their original trajectory link and stage their new verifier archive.
The archive includes check records and RewardKit's criterion reasons and usage.
Errors also keep their available output.
Trials with saved workspace artifacts also keep a trial archive beside those release assets.
The archive contains `result.json`, `lock.json`, agent files, and the artifact manifest and files Harbor needs for regrade.
The same publication check covers these files before they enter an artifact or release.
The planner fetches published trajectories, verifier archives, and trial archives into its saved-work cache.
Older contract rows can use their CI artifacts while those artifacts remain available.
The publisher also runs when a CI run contains regrades and no agent trials.

`publish-results` writes `combined/rows.jsonl`, `combined/release.json`, and `combined/assets/` locally.
Without `--publish`, it performs no remote writes.
With `--publish`, it records rows and release URLs on `ci/results` before uploading assets.
It folds `origin/main`, `origin/ci/results`, and artifact rows onto current `main`, without a force push.
The results pull request contains only the rows change.
The release uses the source commit and workflow run ID. Uploads send 10 files, then pause for 20 seconds.
Rate-limit replies trigger growing waits; failed uploads keep the release and its uploaded files.
Use "Re-run failed jobs" to continue publication. The publisher skips files with matching sizes and replaces incomplete files.
"Re-run all jobs" replans from recorded rows and skips publication when no trials or regrades remain.
A retry also reopens a missing results pull request without another push.

`ethevals publish-logs --output DIR --repo OWNER/REPO --run-id ID --commit SHA` stages a trial release locally.
Adding `--publish` uploads it through `gh` and saves a receipt under `DIR/published/`.

`ethevals export-hf --output DIR` copies every Harbor task folder to an empty directory.
It writes `registry.json`, Harbor metadata in `eval.yaml`, and the dataset card.
Task files remain unchanged. Published folders combine pillar and directory name under `tasks/`.
Registry entries use each task's `[task].name`.
`--hf-repo` and `--license` set dataset card values.
`scripts/ci.py release` previews the HF upload; `--publish` performs it.
The upload removes obsolete task files and the old Concepts task `data/` exports in the same HF commit.
[release.yml](../.github/workflows/release.yml) pushes shared images to GHCR before uploading every task to `buidlguidl/ethevals-test`.
It runs on pushes to `main`, except results-only changes, with `HF_TOKEN` and the workflow's GHCR token.
It tags dataset changes `gh-<short sha>` and supports manual reruns without inputs.
`scripts/ci.py images` builds shared images locally with the same pinned GHCR tags used by the source tasks.
Its `--publish` flag pushes Linux amd64 and arm64 images.
Pull-request, fork, and paid-trial jobs build locally, so they need no prior image release.
See [Dataset publication](../docs/harbor.md#dataset-publication) for standalone Harbor commands.

## Maintainer checks

Use Python 3.13, uv, Node.js 22 or later, pnpm 9.14.2, and Docker with Compose.
Keep provider keys and the Claude plan token unset for free work.
From the repository root, run these commands in one shell:

```sh
unset OPENROUTER_API_KEY ANTHROPIC_API_KEY OPENAI_API_KEY ANTHROPIC_AUTH_TOKEN EXA_API_KEY CLAUDE_CODE_OAUTH_TOKEN
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
