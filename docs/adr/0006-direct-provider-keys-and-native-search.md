---
status: accepted
---

# Use direct provider keys and native search

Claude Code uses Anthropic directly, and Codex CLI uses OpenAI directly, with each provider's own search.
This matches how people use those agents. Their bare models and the grader use direct keys too.
Kimi and GLM stay on OpenRouter in OpenCode with Exa.

Before paid work, the runner requires the keys for the selected providers and the grader.
The keys stay on the host. Exa's key remains optional.

The plan reserves eight searches per Claude Code search call, multiplied by the session cap and the native-search price.
Codex receives the same reserve, although its search count is not capped. The reserve is not a billing ceiling.
Results add native-search fees from the log to token costs.
