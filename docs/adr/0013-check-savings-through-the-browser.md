---
status: accepted
---

# Check Savings through the browser

The Savings discovery task accepted any compiling project, including its untouched starting files.
It now checks the page with Chromium and an injected EIP-1193 wallet after the agent stops.
Shiv approved these checks on 2026-10-24.

The task installs the browser and its dependencies under root-only directories in its own main image.
The agent gets the same tools as the discovery trials.
The verifier forks the task chain into a local Anvil process and funds a fresh test wallet there.
Snapshots isolate journeys without changing the filtered sidecar or the runner.
Browser RPC requests reach this fork through Playwright routing, including requests to the task's Docker hostname and Vite proxies.
The verifier never edits the agent's source.

Checks use wallet requests, chain balances, and visible page values.
They cover deposits, interest-inclusive balances, compounded APY, partial withdrawals, and closing a position through the page's Max control.
They also cover USDT's leftover allowance and refusing a supply above the cap.
A wallet that advertises atomic calls must complete a deposit in at most one onchain transaction.
Its bundle executes through a self-authorized account contract in one transaction; separate calls cannot pass as a bundle.
The cap check fails only for a doomed supply request, rather than an approval request.
Missing controls fail the affected checks and leave screenshots and page text for review.

A binary RewardKit judge criterion checks whether the refused deposit explains the supply cap in words.
It reads the saved page text and screenshot, with the trajectory and guard required by ADR 0011.
A second criterion reads the project's source and follows Deposit and Withdraw through the network switch and the original transaction.
Shiv replaced the scripted wrong-network check with this source criterion on 2026-10-24.
The browser journeys run on mainnet only.
The source snapshot excludes dependencies and build output.
Free checks skip both paid criteria and run every scripted check.
RewardKit remains the only writer of rewards, with all checks required to pass.

This decision adds task checks only.
It changes neither result identity nor paid-run admission.
