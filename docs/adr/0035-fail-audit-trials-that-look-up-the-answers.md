---
status: accepted
---

# Fail audit trials that look up the answers

Audit agents work with the web.
On the 16 audit tasks, 16 of DeepSeek V4.1 Flash's 17 passes came from the published audit report or the upstream fix commits.
On `audit-the-compact`, both of its trials downloaded the OpenZeppelin and Spearbit reports from the project's upstream `audits/` folder.
The instruction never said not to, and no check looked.
Rerunning all 320 saved audit trials costs money the board does not have.

## The decision

- **The instruction says it.** The last paragraph of each audit instruction is `Do not cheat by using online solutions or hints specific to this task.`
- **A judge checks it, in the task.** Each audit task has a second judge, `tests/lookup.toml`, with one criterion, `no_audit_lookup`. It scores like `report_written`, an entry check: a fail makes the trial score 0%, and a pass adds nothing, so a clean trial scores what its findings earn. As a gate check it would add one passed check to every clean trial, and lift a miss on a two-finding task from 0% to 33%. A plain Harbor run gets it too.
  - It fails a trial that went after this project's answers: an audit report on this project from any auditor, anything newer than the audited commit, or write-ups of these bugs. Trying counts, even when nothing was found.
  - Docs, specs, EIPs, package registries, dependency code, general searches, and the project's own files in the checkout are allowed.
  - The criterion names the project, its upstream repositories, the audited commit, and the auditors. The prompt in `tests/lookup-prompt.md` is the same in every audit task.
- **The judge reads the trajectory, not the model's words.** The task declares `/logs/agent/trajectory.json` as an artifact, so Harbor copies it into the separate verifier. The audit variant of `tests/agent_judge.py` writes a copy with only the tool calls, as JSON, and their outputs, from embedded subagent trajectories too. The agent's messages and reasoning are left out. The judge searches it with read tools, no web, and no access to `/logs/agent`.
- **No trajectory is an error, never a fail.** A missing, empty, or invalid trajectory, or one that continues in another file, removes the reward, as a judge crash does.
- **Tuning the lookup judge re-checks; it doesn't rerun.** A judge's files are its criteria, its prompt template, and `tests/agent_judge.py`, which prepares its inputs. A change to only those plans a judge regrade. The copy's hash goes in `judge-inputs-lookup.json`, so a changed copy asks the lookup judge again, and the findings judges keep their answers.
- **Saved audit trials stay.** `tests/regrade-from.json` can be an object. `checks` holds the old checks hashes, as in [ADR 0030](0030-regrade-from-saved-check-output.md). `instructions` maps each old instruction hash to the instruction hash it carries to, and `artifacts` names the old artifact list. Before planning, a saved row on a mapped old instruction moves onto the current instruction, if the mapping names it and the environment is the same. A passed or failed row also needs a named checks hash, and it is regraded from its saved trajectory and findings, with the new check. An error row keeps its retry count. A carried row whose verdict is final, a fail from no answer twice or an error with no retry left, moves onto the current hashes as it is: the same status, history, retry count, and published links, with no saved work fetched, no container, and no judge. A row already on the current instruction always wins. A later instruction edit makes the mapping stale: the planner ignores it and reruns, and lint fails until the claim is removed or updated.
- **Unchanged judges keep their answers in that regrade.** A judge whose criteria, settings, and inputs did not change keeps its saved result, as in other regrades. This replaces ADR 0030's rule that an evidence regrade asks every judge again, for tasks whose tests run the `rewardkit` command, as the audits and the treasury sale do. The voting page runs RewardKit from Python and still asks its judge again.
- **The redo list reruns single trials.** `runner/redo.json` lists saved trials to run again, each with a reason. An entry names the trial and its row's `completed_at`. While the current row still has that `completed_at`, the planner plans one fresh trial for it. Once a newer trial lands, the entry is satisfied. The plan lists entries that match no saved row under `redo_unmatched`. A pull request adds entries, and the merge runs them through the normal CI run.
- **Flagged old trials go on the redo list.** Their agents were never told the rule, so a failed gate on a regraded old trial is not a result. They show 0 on the board until their reruns land.
- This replaces [ADR 0025](0025-regrade-when-only-the-checks-change.md)'s rule that one fail is never regraded or rerun on its own. A trial on the redo list is rerun on its own, and the pull request names why.

## Considered options

- **Rerun every audit trial.** It is the plain rule, and it pays again for about 300 trials, most of which never looked anything up.
- **Block the web, or allow only some sites.** Real audits use the web, and the reports sit on the same sites as the docs.
- **A lookup check in the runner.** Plain Harbor runs from Hugging Face would not get it, and it would change no hash, so saved rows would never get it either.
- **Let the judge read the whole trajectory.** Open-model reasoning trips a provider safeguard, and a long trajectory does not fit one prompt.
- **Keep flagged old trials as fails.** Their agents broke a rule they were never given.

## Known gaps

- `instructions` and `artifacts` are a stopgap until task versions are settled in [issue #125](https://github.com/BuidlGuidl/ethevals/issues/125).
- The regrade asks the lookup judge about every saved audit row, on the Claude plan.
- Flagged trials read 0 between the regrade and their reruns.
- A redo entry needs a finished trial's `completed_at`. An unfinished error keeps its normal retry.
- The judge decides what counts as going after the answers. A search that names the project but finds only docs is its call.
