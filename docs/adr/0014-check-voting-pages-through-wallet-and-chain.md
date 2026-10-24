---
status: accepted
---

# Check voting pages through the wallet and chain

Voting page checks compare visible values and wallet requests with the verifier fork.
Each check records an unreadable value or unfinished flow as "could not drive" and continues.
A known failed check gives reward zero even when another check cannot finish.
If no check fails, unresolved checks cause a trial error after RewardKit records the checks.
RewardKit remains the only reward writer.

Proposal discovery follows visible tabs, pagination, and detail links.
Vote journeys finish when the wallet receives a castVote request.
For journeys require support 1 in both the request and the event.
Wrapping and delegation can share one action.

The task uses no source judge.
Setup generates random keys inside the chain container.
The verifier finds holders through public logs and impersonates them only on its fork.
Extra proposals on the task chain do not prevent checks.
