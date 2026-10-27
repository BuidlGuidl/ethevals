---
status: accepted
---

# Isolate browser verification from agent code

Frontend tasks need to check the page, its wallet requests, and the resulting chain state.
The filtered task chain blocks the funding controls and snapshots that these checks need.
Running agent build scripts with verifier privileges also lets those scripts change the checks or read their keys.

A task verifier can start its own unfiltered fork beside the filtered task chain.
It reads the trusted chain context from `/chain`, funds a fresh wallet, and keeps its key outside the page.
The verifier can advance time and restore snapshots without changing the task chain.
Check-specific state, such as a full cap, belongs in the verifier fork so agents build against the real market.
Fork startup, funding, and fixture failures must produce trial errors rather than failed checks.

Verifier-only tools ship in the task's own image.
The browser, its packages, and its added shared libraries live under root-only directories.
Only the verifier's browser launch receives the library path.
An agent-downloaded browser must still fail to launch without those libraries.
This keeps the agent's tools consistent with the discovery trials.

Build scripts and type checks run as the agent user before the verifier starts its fork.
The verifier kills that user's processes before the build and again after the type check.
No agent process runs alongside the unfiltered fork.
The verifier serves built files with its own static server, without loading agent configuration or following external links.
The tests, evidence, and verifier dependencies remain root-only.

Browser JSON-RPC traffic reaches the fork through request routing.
The page and injected wallet share one read allowlist derived from the filtered task chain's policy.
The wallet handles writes explicitly and records them before execution, including requests that fail or remain pending.
The browser blocks other network endpoints and WebSockets, so page code cannot contact the unfiltered port directly.
The verifier never changes the agent's source.

The task README defines its checks and tolerances.
An injected EIP-1193 wallet also announces itself through EIP-6963.
Its advertised atomic capability uses one transaction for a bundle; non-atomic bundles record separate transactions.
Savings checks do not require atomic deposits; the instruction sets no wallet batching requirement.
RewardKit remains the only reward writer, under ADR 0011.
Guarded criteria can read page evidence or a source snapshot without running the agent's code.
The Savings source criterion follows Deposit or Withdraw through a network switch and the original action.

This decision changes neither result identity nor paid-run admission.
