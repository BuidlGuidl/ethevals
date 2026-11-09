---
status: accepted
---

# Replace Fable 5.1 with Fable 5.2

Fable 5.2 is released. ADR 0022 paused Fable 5.1 and planned to resume it later.
Fable 5.1 does not resume. Fable 5.2 takes its place.

## The decision

Add Fable 5.2's model, Claude Code agent, and vanilla agent to the default job settings.
They use the same payment, cost limits, effort, and modes as the Fable 5.1 entries.
The Claude Code agent uses version 2.1.290, the oldest version that supports Fable 5.2.
Keep the Fable 5.1 entries out. The catalog omits Fable 5.1, so the board keeps it hidden.

Keep every saved Fable 5.1 row and artifact.
Keep task hashes, scoring, retry rules, and the two-trial setting unchanged.
