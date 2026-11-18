---
status: accepted
---

# Add GPT-6.2 Sol

GPT-6.2 Sol is released, with the same id in the API and in Codex CLI.
ADR 0031 waited to add it until every GPT-6.2 Astra trial had finished, because both run on one ChatGPT plan.
The plan now has five banked limit resets for Codex, so a shared limit no longer blocks Sol.

## The decision

Add GPT-6.2 Sol's model, Codex agent, and vanilla agent to the default job settings, beside the models already there.
They use the same payment, cost limits, effort, and modes as the GPT-6.2 Astra entries.
The Codex agent uses version 0.169.1, the same as GPT-6.2 Astra's; it runs GPT-6.2 Sol on the ChatGPT plan.
The other Codex agents keep their versions.

This replaces ADR 0031's line about adding Sol only after every GPT-6.2 Astra trial has finished.
Results runs still go one at a time, so Sol's run waits behind any Astra run still going.

Keep task hashes, scoring, retry rules, and the two-trial setting unchanged.
