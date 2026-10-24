---
status: accepted
---

# Accept prior Safe message signing in the empty-signature quiz

The Safe empty-signature rule rejected correct GPT and Kimi replies from saved trials.
It missed "previously signed Safe message" and "on-chain SafeMessage approval" in their opening answers.

## Decision

Accept an opening answer that names prior or onchain approval of the Safe message.
Read up to two opening sentences, including a sentence after a line break.
Accept `signedMessages`, `signMessage`, and `SignMessageLib` as names for this approval mechanism.
Reject never, always, an uninitialized Safe, and owner `approvedHashes` or `approveHash` alone.
Keep the wrong-opening cases rejected when a later sentence mentions the right mechanism.

Keep the existing hand cases and add all four saved trial replies.
Regrade their copied artifacts through Harbor without new model calls.

## Consequences

Correct replies can earn reward 1 without naming a specific Safe library or mapping.
The task hash changes, so the saved regrades remain separate from the original trials.
The check name and all-pass reward aggregation stay unchanged.
