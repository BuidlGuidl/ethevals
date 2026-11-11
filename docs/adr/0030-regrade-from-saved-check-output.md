---
status: accepted
---

# Regrade from saved check output

The treasury sale has 29 saved rows on checks hash `sha256:bad31e58…`.
Its four remaining code checks have no changed lines.
The two retired code checks became criteria.
Every row's public check output holds the six old records, script source, and chain evidence.
The chain itself is gone.

The voting page has 18 board rows on checks hash `sha256:b26de136…`.
Its compile check and source bundle are unchanged.
Only the judge plumbing changed, and every row saves the bundle and compile record.
Two rows have no saved page code for a fresh trial environment.
Whole-file checks hashes cannot express that code records still stand.

## The decision

- A task can name old checks hashes in `tests/saved-checks.json`, a JSON array of SHA256 hashes.
  For those hashes, its tests claim that the saved code records still stand.
  The planner reads the file without running task code.
  It has no task list or new task setting.
- A passed or failed row with a named hash uses a regrade from saved check output.
  Instruction, environment, and artifact changes still rerun the trial.
  This rule comes before the task's normal regrade kind.
  Other hashes keep their existing treatment.
- The regrade runs the real `tests/test.sh` with saved check output and trajectory.
  It starts no chain, workspace, or agent container.
  `ETHEVALS_REGRADE_ITEM` tells the tests to preserve saved evidence and skip live-trial steps.
  Treasury keeps exactly the code records it still defines and rejects a missing record.
  Voting keeps its compile record, source bundle, and source manifest without building or bundling again.
  Every current judge runs through the task's helper with the plan credential.
  The regrade never reuses saved judge answers.
- Recovery keeps trial identity, agent, model, model cost, and trajectory.
  It replaces checks, status, check output, checks hash, checks generation, regrade time, and judge fields.
  A treasury row has four saved code records and four new criterion answers.
- Saved work uses the judge-only fetch path for trajectory and check output.
  Confirmed missing work plans a rerun.
- A judge-only change with a live judge uses the task's workspace regrade kind when available.
  Otherwise it reruns the trial.
  This replaces ADR 0026's interim live-session rule and extends [ADR 0029](0029-regrade-pages-from-saved-work.md).

The statement is part of the checks hash under the existing hash rules.
Its JSON suffix avoids RewardKit's TOML discovery.

## Considered options

- A kept-check list in the runner puts task rules in shared code.
- Reading judge inputs out of `test.sh` makes shell text a runner interface.
- A field outside `tests/` needs a hash exemption or changes the environment hash.
- Rerunning both tasks repeats model work already saved.
  The broader page changes otherwise rerun 36 board trials.

## Known gaps

- A reviewer must compare the code-check diff with the task's claim.
- Removing the statement alone changes the checks hash.
  Remove it with the next code-check change so older rows fall through to the existing rules.
- Act tasks whose code checks changed in substance still need reruns.
