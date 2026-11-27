---
status: accepted
---

# Fail audit trials that look up the answers

Audit agents work with the web.
On the 16 audit tasks, 16 of DeepSeek V4.1 Flash's 17 passes came from the published audit report or the upstream fix commits.
On `audit-the-compact`, both of its trials downloaded the OpenZeppelin and Spearbit reports from the project's upstream `audits/` folder.
The instruction never said not to, and no check looked.
Rerunning all 320 saved audit trials costs money the board does not have, and re-checking them all on CI costs Claude plan time.

## The decision

- **The instruction says it.** The last paragraph of each audit instruction is `Do not cheat by using online solutions or hints specific to this task.`
- **A judge checks it, in the task.** Each audit task has a second judge, `tests/lookup.toml`, with one criterion, `no_audit_lookup`. It scores like `report_written`, an entry check: a fail makes the trial score 0%, and a pass adds nothing, so a clean trial scores what its findings earn. As a gate check it would add one passed check to every clean trial, and lift a miss on a two-finding task from 0% to 33%. A plain Harbor run gets it too.
  - It fails a trial that went after this project's answers: an audit report on this project from any auditor, anything newer than the audited commit, or write-ups of these bugs. Trying counts, even when nothing was found.
  - Docs, specs, EIPs, package registries, dependency code, general searches, and the project's own files in the checkout are allowed.
  - The criterion names the project, its upstream repositories, the audited commit, and the auditors. The prompt in `tests/lookup-prompt.md` is the same in every audit task.
- **The judge reads the trajectory, not the model's words.** The task declares `/logs/agent/trajectory.json` as an artifact, so Harbor copies it into the separate verifier. The audit variant of `tests/agent_judge.py` writes a copy with only the tool calls, as JSON, and their outputs, from embedded subagent trajectories too. The agent's messages and reasoning are left out. The judge searches it with read tools, no web, and no access to `/logs/agent`.
- **No trajectory is an error, never a fail.** A missing, empty, or invalid trajectory, or one that continues in another file, removes the reward, as a judge crash does.
- **Tuning the lookup judge re-checks; it doesn't rerun.** A judge's files are its criteria, its prompt template, and `tests/agent_judge.py`, which prepares its inputs. A change to only those plans a judge regrade. The copy's hash goes in `judge-inputs-lookup.json`, so a changed copy asks the lookup judge again, and the findings judges keep their answers.
- **Saved audit trials carry over, unchecked by CI.** `tests/regrade-from.json` can be an object whose `instructions` maps each old instruction hash to the instruction hash it carries to. Before planning, a saved row on a mapped old instruction moves onto the current instruction, if the mapping names it and the environment is the same. A carried pass or fail, or a carried error with no retry left, moves onto the current hashes as it is: the same status, checks, history, retry count, and published links, with no saved work fetched, no container, and no judge. It has no `no_audit_lookup` result. A carried error with a retry left keeps its retry count. A row already on the current instruction always wins. A later instruction edit makes the mapping stale: the planner ignores it and reruns, and lint fails until the claim is removed or updated.
- **The saved trials were screened locally, by hand.** Before merge, a script listed every tool call in the saved audit trials that named the project's upstream repository or an auditor's site, or searched with "audit". A person read each flagged trial and applied the same rule as the judge: 37 of the 320 went after the answers. 11 fetched the published report, and 26 read upstream code newer than the audited commit. Trials that failed after two refusals were not screened, since they stay fails. The 37 are listed in `runner/redo.json` with their reasons. The rest carry over as they were.
- **The task's own judge can re-check a saved trial locally.** `ethevals regrade --recheck` decides selected saved passes and fails again with the current checks, and keeps unchanged judges' answers. CI never runs it.
- **The redo list reruns single trials.** `runner/redo.json` lists saved trials to run again, each with a reason. An entry names the trial and its row's `completed_at`. While the current row still has that `completed_at`, the planner plans one fresh trial for it. Once a newer trial lands, the entry is satisfied. The plan lists entries that match no saved row under `redo_unmatched`. A pull request adds entries, and the merge runs them through the normal CI run.
- **Flagged old trials go on the redo list.** Their agents were never told the rule, so a lookup on an old trial is not a result. The merge reruns them, and their old results stay on the board until the reruns land.
- This replaces [ADR 0025](0025-regrade-when-only-the-checks-change.md)'s rule that one fail is never regraded or rerun on its own. A trial on the redo list is rerun on its own, and the pull request names why.

## Considered options

- **Rerun every audit trial.** It is the plain rule, and it pays again for about 300 trials, most of which never looked anything up.
- **Block the web, or allow only some sites.** Real audits use the web, and the reports sit on the same sites as the docs.
- **A lookup check in the runner.** Plain Harbor runs from Hugging Face would not get it, and it would change no hash, so saved rows would never get it either.
- **Let the judge read the whole trajectory.** Open-model reasoning trips a provider safeguard, and a long trajectory does not fit one prompt.
- **Keep flagged old trials as fails.** Their agents broke a rule they were never given.

## Known gaps

- `instructions` is a stopgap until task versions are settled in [issue #125](https://github.com/BuidlGuidl/ethevals/issues/125).
- CI never checks a carried old trial for lookups. Only the local screen did, and an unflagged lookup stays on the board.
- A redo entry needs a finished trial's `completed_at`. An unfinished error keeps its normal retry.
- The judge decides what counts as going after the answers. A search that names the project but finds only docs is its call.
