---
status: accepted
---

# Check voting pages through the wallet and chain

Voting page checks compare visible values and wallet requests with the verifier fork.
Each check records an unreadable value or unfinished flow as "could not drive" and continues.
A known failed check gives reward zero regardless of other checks' errors or missing records.
If no check fails and unresolved checks remain, RewardKit raises a trial error and writes no reward.
RewardKit remains the only reward writer.

Proposal discovery follows visible tabs, pagination, and detail links.
Vote journeys finish when the wallet receives a castVote request.

The task uses no source judge.
Setup generates random keys inside the chain container.
The verifier finds holders through public logs and impersonates them only on its fork.

This decision changes neither result identity nor paid-run admission.
