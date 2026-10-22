---
status: accepted
---

# Verifiers use RewardKit, and criteria run in the task

[ADR 0010](0010-run-tasks-on-harbor.md) moved the board to Harbor, but two older shapes came along.
Our test helpers wrote their own reward and check files. The judge read `criteria.md` on the host after Harbor finished.
So a plain `harbor run` from Hugging Face skipped the criteria, and could give reward 1 to a trial the board failed.
The board also rejected valid RewardKit output.
This ADR moves the verifier to Harbor's own recommended shape, RewardKit as the one writer of the reward.
It also takes Harbor's retry policy and words, drops the board's time limit, and gives every task Harbor's `[task]` table.
It amends ADR 0010.

## The verifier

- **RewardKit writes every reward.** `test.sh` runs RewardKit over the task's tests. RewardKit alone writes `reward.json` and `reward-details.json`. No helper writes `reward.txt` or `reward.json` itself.
- **Test tools still write check records:** a name, pass or fail, and a one-line reason. A shared RewardKit check in the shared images turns each record into a named criterion that carries its reason. Forge and the quiz have helpers. Any other tool fits the same way.
- **The quiz is a RewardKit check.** It reads the final reply from the ATIF trajectory, because the vanilla agent has no tools to write a file. Inspect's matcher fields (`target`, `location`, `ignore_case`) leave the task folder.
- **`reward` is `all-pass` over every check and criterion.** The board's pass is Harbor's `reward == 1`, so the board and a plain Harbor run can't disagree. Other reward keys are allowed and kept. The board's checks come from `reward-details.json`.
- **RewardKit stays pinned** to the version in the repo. A verifier with no judge needs no network.

## Criteria

- **A RewardKit judge file in `tests/` replaces `criteria.md`.** It's RewardKit's own TOML format. Lint holds the board's rules:
  - binary criteria only
  - every criterion has a name
  - the judge reads the agent's ATIF trajectory
  - the judge's guard is on
  - criteria count toward the `all-pass` reward like any other check
- **The judge runs in the verifier.** Anyone who runs the task gets the criteria, with the file's judge as the default. The board sets the judge's model and effort from the job config, so every task gets the same judge.
- **The judge's key comes through `[verifier.env]`.** A task with a judge file may name exactly the judge key there and no other credential. A plan token never reaches the judge, because ADR 0010 rules out a plan for RewardKit.
- **Without the key, the user is told so.** It's a clear message, not a silent 0. The free check still needs no secrets and no model, and it still proves the tests.
- **A judge error is a trial error,** not a failed check. Retrying it never quietly reruns the agent's work. Harbor's `trial regrade`, which reruns only the verifier on a saved trial, is the starting point.
- **The judge's cost** comes from its usage in `reward-details.json`. It joins the trial's cost, and the budget still reserves it.

## Retries

- **Harbor's words.** `n_attempts` is how many scored trials a job runs for each task, agent, and mode. A retry runs a trial again after an error and adds no scored trial. The board sets `retry.max_retries` to 1.
- **Harbor's exclusion list decides which errors get a retry.** In Harbor 0.24.0, these never do:
  - timeouts: `AgentTimeoutError` and `VerifierTimeoutError`
  - broken reward output: `RewardFileNotFoundError`, `RewardFileEmptyError`, and `VerifierOutputParseError`
  - account and model problems: `ApiUsageLimitError`, `AgentSafetyRefusalError`, `AgentAuthenticationError`, and `ModelNotFoundError`
- **Our own parts stay.** The board still recovers missing trials across runs and admits spend against the budget.

## Time limits

- **The board sets no time limit.** Trials run with Harbor's defaults, unless a task sets its own `[agent]` or `[verifier]` `timeout_sec`. A task sets one only when it needs it.
- **What reaches a limit shows as a timeout** on the board.
- **Rows and trial identity carry no board-wide limit.**
- **CI's step timeout for each trial is the backstop.**

## Package info

- **Every task has Harbor's `[task]` table:** a stable `name` under the `buidlguidl` org, a `description`, `authors`, and `keywords`. The description replaces `metadata.motivation`. Pillar and modes stay in metadata.
- **A task's name is the same everywhere:** in the repo, in the Hugging Face `registry.json`, and in a plain Harbor run of the export.

## Known gaps

- **The judge key sits in the verifier.** For a chain task, that's the agent's container after the agent stops, and nothing freezes a process the agent left running there. The board uses a judge-only key with its own spend limit.
- **Locally, nothing stops a stuck trial** whose agent has no budget flag, such as OpenCode on OpenRouter. On CI, the step timeout does.
- **A judged task costs outside users money.** Running it from Hugging Face needs the user's own judge key.

## Considered options

- **Keep the judge on the host.** The key never enters a container, but a plain Harbor run skips the criteria. Then what we publish isn't what we run, which was one of ADR 0010's reasons to switch.
- **Let each test tool write `reward.txt`, as Harbor's pytest option does, and add a judge next to it.** That makes two writers, and Harbor reads `reward.json` before `reward.txt`.
- **Set time limits in every task, and lint them against the job config.** That keeps limits explicit, but it adds a rule that no task needs yet.
- **Run every chain task's verifier separately,** to keep the judge key away from the agent's container. The chain stops before the tests can read it, as ADR 0010 found.

## Changes to ADR 0010

- **Records feed RewardKit.** `test.sh` still writes one record per check, and RewardKit reads them and writes the reward.
- **Criteria are a RewardKit judge file,** run by the verifier rather than on the host.
- **The job config no longer holds a time limit.** "No task sets its own time limit" is reversed: a task sets one when it needs it.
- **"Attempt" becomes Harbor's "retry",** and `trials` becomes `n_attempts`.
- **A passing trial now means `reward == 1`,** which is still every check passing.
