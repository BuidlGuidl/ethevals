---
status: accepted
---

# Check voting pages through captures, the wallet and the chain

Six rounds of saved pages exposed valid wording that the verifier's text readers rejected.
A RewardKit judge now compares captured page text with the governor's values at each captured moment.
It decides every check about what the page shows.

Code drives connection, tabs, pagination, proposal views, wrapping, delegation and voting.
It checks wallet requests, including each recipient, proposal and vote support.
It checks balances, `getVotes`, and `VoteCast` weights on the verifier fork.
Compilation and the presence of each chosen proposal title stay code checks.

The judge reads only `/logs/verifier/page-evidence.txt`, a plain-text file with captured views, governor values and wallet facts.
Repeated views share a text entry to reduce judge input.
Captures include list views, each available proposal view, wrap and delegation views, and views around votes.
The judge reads neither the trajectory nor the agent's source.

Any wording, number format or end unit passes when it conveys the required values.
A missing requested value or a value that contradicts the governor fails.
For an old proposal, the holder must see zero snapshot votes or send no vote request.
A successful zero-weight receipt cannot excuse a page that shows only current votes and asks for that vote.

The fork adds a Pending proposal and cancels it through its proposer.
The page must show it as canceled and send no vote request for it.
It counts toward proposal discovery.
A holder who already voted on an open proposal must send no second vote request.
These proposals and votes exist only on the verifier fork.

An unfinished flow records "could not drive" in code and `captured=false` in the judge input.
The judge passes that criterion because it cannot decide from an uncaptured view.
A known failed code check or judge criterion gives reward zero.
If no check fails and unresolved checks remain, the verifier raises a trial error and keeps no reward.
RewardKit remains the only reward writer.

The judge is `anthropic/claude-opus-5-5` at high effort with `guard = "flag"`, matching the board.
Binary criteria join code checks under `all-pass`.
Only `ANTHROPIC_API_KEY` enters through `[verifier.env]`.
Builds and browser processes receive no model keys.
The free check drops judge files and checks that code still separates the solution and untouched project.

Hand cases cover every saved page, wrong values and correct wording absent from those pages.
Every case must receive its expected mark in two separate judge runs.
Judge cost comes from usage in `reward-details.json`.
Saved-page runs cost $0.021 to $0.524 per trial.
The largest capture exceeds the aim of less than $0.50 per trial.

The task uses no source judge.
Setup generates random keys inside the chain container.
The verifier finds holders through public logs and impersonates them only on its fork.

This decision changes neither result identity nor paid-run admission.

[ADR 0019](0019-fail-voting-pages-that-claim-no-proposals.md) adds a judge for empty claims and proposal load errors.

## Known gaps

- The judge reads text from the agent's page, so a page could add words aimed at the judge. `guard = "flag"` records such an attempt in `reward-details.json` without changing the reward. It flagged none of the 16 saved-page runs.
- A judged trial costs one judge call, up to $0.52 on the longest saved page, and a plain Harbor run needs the user's own judge key.
- The canceled and already-voted checks failed no saved page. They cover cases a page could get wrong, not misses seen in trials.
