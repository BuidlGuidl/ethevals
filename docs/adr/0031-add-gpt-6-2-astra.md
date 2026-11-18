---
status: accepted
---

# Add GPT-6.2 Astra

GPT-6.2 Astra is released, with the same id in the API and in Codex CLI.
GPT-6.2 Sol is released too, but both run on one ChatGPT plan,
and Astra uses the plan limit about three times faster than Sol.

## The decision

Add GPT-6.2 Astra's model, Codex agent, and vanilla agent to the default job settings, beside the models already there.
They use the same payment, cost limits, effort, and modes as the GPT-6 Astra entries.
The Codex agent uses version 0.169.1, the oldest version that runs GPT-6.2 Astra.
Codex 0.163.0 has no entry for the model, and the ChatGPT plan refuses it from that version.
The other Codex agents stay on 0.163.0.

Add GPT-6.2 Sol in a later release, after every GPT-6.2 Astra trial has finished, so the two do not share the plan limit.

Keep task hashes, scoring, retry rules, and the two-trial setting unchanged.
