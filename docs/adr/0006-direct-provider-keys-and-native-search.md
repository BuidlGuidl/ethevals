---
status: accepted
---

# Use direct provider keys and native search

Claude Code uses Anthropic directly, and Codex CLI uses OpenAI directly, with each provider's own search.
Codex runs GPT-5.5 because Codex routes GPT-6 models through a search endpoint that Inspect's bridge does not support yet.
This matches how people use those agents. Their bare models and the grader use direct keys too.
Kimi and GLM stay on OpenRouter in OpenCode with Exa.

Before paid work, the runner requires the keys for the selected providers and the grader.
The keys stay on the host. Exa's key remains optional.

Plans reserve agent and grader token costs for all remaining attempts.
Search charges sit outside the plan and results costs.
Claude Code keeps its session search cap; Exa caps search and fetch calls per epoch. Codex search has no cap.
