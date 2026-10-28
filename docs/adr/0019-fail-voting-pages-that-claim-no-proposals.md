---
status: accepted
---

# Fail voting pages that claim no proposals

A voting page can fail to load proposals while the governor has proposals.
The page's own empty count or load error proves a failure.
A missing list alone proves no failure because the verifier can miss a tab or view.
That case still records "could not drive" and needs human review if no check fails.

A separate RewardKit criterion, `shown_proposal_list`, reads `/logs/verifier/proposal-list-evidence.txt`.
The file holds captured list views, the governor's proposal count and titles, and the titles code found.
If code finds any titles, the criterion passes and `lists_every_proposal` checks whether it found every title.
If code finds no titles in a governance view, the judge compares the page's claims with the governor.
An empty claim, a contradictory proposal count, or a proposal load error fails.
A view without those claims passes this criterion, and the code check stays "could not drive".
Without a governance control or proposal titles, code fails the untouched project as before.

The criterion uses `anthropic/claude-opus-5-5` at high effort with `guard = "flag"`.
It shares no criteria or evidence file with the existing page-value judge.
Builds and browser processes receive no model keys.
The free check skips both judges and still requires oracle 1 and nop 0.

The judge replaces the old explicit-empty text reader.
Delegation also accepts "Update delegation" as a submit control.
A click without a delegate wallet request still records "could not drive".

The new judge adds one call per trial.
Across four saved-page trials, it cost $0.015112 to $0.022612 per trial, measured from RewardKit usage.
Both repeats of the page with a load error received reward 0 without a trial error.
The solution and a second correct saved page passed every check and criterion.
All six list hand cases received their expected marks in two separate judge runs.
The 20 judge calls for these checks cost $0.554248, below the $3 budget.
This decision changes neither result identity nor paid-run admission.
