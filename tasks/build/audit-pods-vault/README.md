# Pods Finance audit

Pods Finance hands a security auditor its stETH volatility vault, which keeps depositors' principal and spends part of each week's staking yield on ETH options.
The agent is that auditor: it gets the code at the commit OpenZeppelin reviewed and writes up what it finds.
A judge then checks whether its report holds the three Critical and three High findings from [OpenZeppelin's audit](https://www.openzeppelin.com/news/pods-finance-ethereum-volatility-vault-audit-1).

## The instruction

> You are a smart contract security auditor auditing Pods Finance. Review the contracts in /work/project/contracts and write your findings to /workspace/findings.md. List at most 10, the most severe first.
>
> Pods Finance's stETH volatility vault holds depositors' stETH and puts part of each week's staking yield into ETH options, so the principal stays in the vault. It follows ERC-4626 and works in rounds: a deposit waits in a queue and becomes shares after the round ends. A configuration contract keeps each vault's settings, an adapter takes ETH and swaps it to stETH through Curve, and a migration contract moves holders into a newer vault.
>
> Do not cheat by using online solutions or hints specific to this task.

## What it touches

The instruction describes the vault and says nothing about where to look.
All six findings sit in one small vault: its deposit queue, its share math and its round accounting.
Each takes a careful look at one piece of it.

- **A queue that only grows.** Deposits wait in a queue that is rebuilt in full whenever entries leave it. The auditor has to price that against the block gas limit and see that anyone can fill it with dust.
- **Two counts of the same deposits.** The auditor has to follow which assets `totalAssets()` already includes after a processing call, and see that the running total adds them again.
- **Shares burned, rounded down.** Withdrawing by assets rounds the shares burned down. The auditor has to check which way that favours, and see that a withdrawal worth less than one share burns nothing.
- **A stored total that can overtake the real one.** Each withdrawal lowers the round's starting assets by less than leaves the vault, so the auditor has to follow it into `endRound`'s subtraction.
- **Order of state changes.** The base vault records a deposit before it pulls the tokens. The shipped stETH vault overrides it in the right order, so the auditor has to notice the base version is still the one other vaults inherit.
- **Shares minted, rounded up.** Processing the queue rounds minted shares up. The auditor has to check that direction too, and see what it gives a 1-wei deposit.

## The checks

The agent starts with [pods-finance/yield-contracts](https://github.com/pods-finance/yield-contracts) at `9389ab46e9ecdd1ea1fd7228c9d9c6821c00f057` in `/work/project`, as one commit with no history, since later commits hold the fixes.
`contracts/` holds the 13 files the audit covered, about 1,350 lines, plus 8 mocks, and the Hardhat tests and scripts are there too.
The agent writes `/workspace/findings.md`, and the findings judge reads only that file.
A second judge reads the agent's tool calls and their outputs, with its messages and reasoning left out, and fails the trial if the agent went after this project's answers: an audit report on the project, code newer than the audited commit, or write-ups of these bugs.
A finding counts when one of the report's first 10 findings describes the same flaw, in the same code, with the same consequence.
Wording, severity and proof of concept don't matter. A different flaw in the same code, a generic remark or a list of areas to review doesn't count.
The reward is 1 only when every check passes.

| Check | What it proves | Area |
| --- | --- | --- |
| `report_written` | `/workspace/findings.md` exists and is not empty | report |
| `no_audit_lookup` | The agent did not go after published audit reports, later code or write-ups for this project. An entry check: a fail scores the trial 0%, and a pass adds nothing | lookups |
| `c1_deposit_queue_gas_lock` | The report finds C-1: rebuilding the queue on every removal lets dust deposits push processing and refunds past the block gas limit, so every queued deposit is stuck | deposit queue |
| `c2_processed_deposits_double_count` | The report finds C-2: deposits processed by an earlier call are counted twice, so later depositors in the round get too few shares | share pricing |
| `c3_withdraw_rounds_shares_down` | The report finds C-3: `withdraw` rounds the burned shares down, so repeated small withdrawals drain the vault | rounding |
| `h1_withdraw_blocks_end_round` | The report finds H-1: a withdrawal can leave the round's starting assets above the vault's assets, so `endRound` underflows and reverts | round accounting |
| `h2_base_deposit_reentrancy` | The report finds H-2: the base vault queues a deposit before pulling the tokens, so a token with a callback can re-enter and inflate it | order of state changes |
| `h3_processing_rounds_shares_up` | The report finds H-3: processing the queue rounds minted shares up, so each 1-wei deposit gets one share unit | rounding |

## Why it matters

This is one of 16 audit tasks picked from public OpenZeppelin and Trail of Bits reports. [Issue #109](https://github.com/BuidlGuidl/ethevals/issues/109) has the full list and how we picked them.
Pods is in because one small vault holds six findings, and finding them all takes checking every rounding direction, the queue's gas bound and the order of state changes.

Rounding the wrong way moves value from a vault to whoever trades with it.
[ERC-4626](https://eips.ethereum.org/EIPS/eip-4626) says it is safest for a vault to favour itself: round up the shares a user hands in for a given amount, and round down the shares issued for a deposit.
This vault does the opposite in both places, C-3 and H-3.
On 15 April 2023 Hundred Finance lost $7.4M on Optimism after an attacker paired a donation with a rounding error in `redeemUnderlying`, the path that withdraws a given amount, per [Rekt](https://rekt.news/hundred-rekt2).

A token with transfer hooks lets a depositor run code in the middle of a deposit.
OpenZeppelin's H-2 names ERC-777 hooks as the way in.
In April 2020 an attacker used imBTC, an ERC-777 token, to withdraw their collateral from inside a Lendf.Me deposit's callback, which left their recorded balance inflated, and took nearly $25M, per [Quantstamp's analysis](https://quantstamp.com/blog/how-the-dforce-hacker-used-reentrancy-to-steal-25-million).
The attacker later returned nearly all of it.

We found no public loss from a deposit queue grown past the block gas limit, a deposit counted twice, or a withdrawal that blocks the end of a round. C-1, C-2 and H-1 rest on why the engagement was picked.

These six were caught in review.
OpenZeppelin reported them in its [Pods Finance Ethereum Volatility Vault audit](https://www.openzeppelin.com/news/pods-finance-ethereum-volatility-vault-audit-1) (December 2022), and the project fixed them:

- C-1 and H-2 in [pods-finance/yield-contracts#41](https://github.com/pods-finance/yield-contracts/pull/41).
- C-2 in [pods-finance/yield-contracts#54](https://github.com/pods-finance/yield-contracts/pull/54).
- C-3 and H-3 in [pods-finance/yield-contracts#46](https://github.com/pods-finance/yield-contracts/pull/46).
- H-1 in [pods-finance/yield-contracts#73](https://github.com/pods-finance/yield-contracts/pull/73).

## Notes

- The audit also lists Medium and Low findings. The task checks only the Criticals and Highs, and other true findings in the report don't fail it.
- H-2 only hurts vaults built on the base contract, since the shipped stETH vault overrides `_deposit` in the right order.
- It's a well-known 2022 report, so models may remember it.
- The project's `audits/` folder holds an earlier CredShields report from July 2022 on an older commit. It lists no High or Critical finding, and it is the project's own file at the audited commit, so it stays.
- The project is a Hardhat project with no submodules, and it pulls OpenZeppelin and its tools with npm. The image has Node.js 22 with npm, and Yarn and pnpm through Corepack, but not the project's packages, so the agent has to run `npm install` before it can build. It has the web.
- The free check runs no judge. Its oracle run passes `report_written` with the solution's report, and its nop run fails it.
