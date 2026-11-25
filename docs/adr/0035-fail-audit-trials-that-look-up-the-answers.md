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
- **A judge checks it, in the task.** Each audit task has a second judge, `tests/lookup.toml`, with one criterion, `no_audit_lookup`, tagged `gate`. A plain Harbor run gets it too.
  - It fails a trial that went after this project's answers: an audit report on this project from any auditor, anything newer than the audited commit, or write-ups of these bugs. Trying counts, even when nothing was found.
  - Docs, specs, EIPs, package registries, dependency code, general searches, and the project's own files in the checkout are allowed.
  - The criterion names the project, its upstream repositories, the audited commit, and the auditors. The prompt in `tests/lookup-prompt.md` is the same in every audit task.
- **The judge reads the trajectory, not the model's words.** The task declares `/logs/agent/trajectory.json` as an artifact, so Harbor copies it into the separate verifier. `tests/judge_trajectory.py` writes a copy with only the tool calls and their outputs. The agent's messages and reasoning are left out. The judge searches it with read tools and no web.
- **No trajectory is an error, never a fail.** The verifier removes the reward, as it does when a judge crashes.
- **Saved audit trials stay.** `tests/regrade-from.json` can be an object. `checks` holds the old checks hashes, as in [ADR 0030](0030-regrade-from-saved-check-output.md). `instructions` names old instruction hashes, and `artifacts` names the old artifact list, whose saved trials still stand. A passed or failed row on a named instruction and a named checks hash is regraded from its saved trajectory and findings, with the new gate. The new row carries the current instruction hash, so the board shows it. An error row on a named instruction keeps its retry count.
- **Unchanged judges keep their answers in that regrade.** A judge whose criteria, settings, and inputs did not change keeps its saved result, as in other regrades. This replaces ADR 0030's rule that an evidence regrade asks every judge again.
- **The redo list reruns single trials.** `runner/redo.json` lists saved trials to run again, each with a reason. An entry names the trial and its row's `completed_at`. While the current row still has that `completed_at`, the planner plans one fresh trial for it. Once a newer trial lands, the entry is satisfied. A pull request adds entries, and the merge runs them through the normal CI run.
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
