# Pods Finance audit

The agent audits Pods Finance's stETH volatility vault at the commit OpenZeppelin reviewed and writes a findings report.
A judge then checks whether the report's first 10 findings hold each Critical and High finding from [OpenZeppelin's audit](https://www.openzeppelin.com/news/pods-finance-ethereum-volatility-vault-audit-1), one question per finding.

## The instruction

> You are a smart contract security auditor auditing Pods Finance. Review the contracts in /work/project/contracts and write your findings to /workspace/findings.md. List at most 10, the most severe first.
>
> Pods Finance's stETH volatility vault holds depositors' stETH and puts part of each week's staking yield into ETH options, so the principal stays in the vault. It follows ERC-4626 and works in rounds: a deposit waits in a queue and becomes shares after the round ends. A configuration contract keeps each vault's settings, an adapter takes ETH and swaps it to stETH through Curve, and a migration contract moves holders into a newer vault.

## What it touches

The image clones [pods-finance/yield-contracts](https://github.com/pods-finance/yield-contracts) at `9389ab46e9ecdd1ea1fd7228c9d9c6821c00f057`, the commit the audit names.
It deletes the git history, since later commits hold the fixes, and starts a fresh repo with one commit at `/work/project`.
`contracts/` holds the 13 files the audit covered, about 1,350 lines, plus 8 mocks. The Hardhat tests and scripts are there too.
The project is a Hardhat project with no submodules. It pulls OpenZeppelin and its tools with npm, and the image has no Node.js, so the agent would have to fetch Node and the packages itself. It has the web.

The six findings sit in one small vault, and each takes a careful look at one piece of it:

- **A queue that only grows.** Deposits wait in a queue that is rebuilt in full whenever entries leave it. The auditor has to price that against the block gas limit and see that anyone can fill it with dust.
- **Two counts of the same deposits.** The auditor has to follow which assets `totalAssets()` already includes after a processing call, and see that the running total adds them again.
- **Rounding in both directions.** Withdrawing by assets rounds the burned shares down, and processing the queue rounds minted shares up. The auditor has to check every rounding direction and see who it favours.
- **A stored total that can overtake the real one.** Each withdrawal lowers the round's starting assets by less than leaves the vault, so the auditor has to follow it into `endRound`'s subtraction.
- **Order of state changes.** The base vault records a deposit before it pulls the tokens. The shipped stETH vault overrides it in the right order, so the auditor has to notice the base version is still the one other vaults inherit.

## The checks

The verifier copies `/workspace/findings.md` to `/logs/verifier/findings.md` and gives that file to the judge.
Each finding counts when one of the report's first 10 findings names the same flaw, in the same code, with the same consequence.
Wording, severity and proof of concept don't matter. A different flaw in the same code, a generic remark, a list of areas to review, or the mechanism placed where it does no harm doesn't count.
The reward is 1 only when every check passes.

| Check | What it proves | Area |
| --- | --- | --- |
| `report_written` | `/workspace/findings.md` exists and is not empty | report |
| `c1_deposit_queue_gas_lock` | The report finds C-1: rebuilding the queue on every removal lets dust deposits push processing and refunds past the block gas limit, so every queued deposit is stuck | deposit queue |
| `c2_processed_deposits_double_count` | The report finds C-2: deposits processed by an earlier call are counted twice, so later depositors in the round get too few shares | share pricing |
| `c3_withdraw_rounds_shares_down` | The report finds C-3: `withdraw` rounds the burned shares down, so repeated small withdrawals drain the vault | rounding |
| `h1_withdraw_blocks_end_round` | The report finds H-1: a withdrawal can leave the round's starting assets above the vault's assets, so `endRound` underflows and reverts | round accounting |
| `h2_base_deposit_reentrancy` | The report finds H-2: the base vault queues a deposit before pulling the tokens, so a token with a callback can re-enter and inflate it | order of state changes |
| `h3_processing_rounds_shares_up` | The report finds H-3: processing the queue rounds minted shares up, so 1-wei deposits each get a whole share | rounding |

## Why it matters

A vault's shares are a claim on everyone's deposits, so a rounding or counting error moves money from one depositor to another, and a queue that can't be processed locks all of it.
OpenZeppelin's [Pods Finance Ethereum Volatility Vault audit](https://www.openzeppelin.com/news/pods-finance-ethereum-volatility-vault-audit-1) (December 2022) found these six flaws, and the project fixed them:

- C-1 and H-2 in [pods-finance/yield-contracts#41](https://github.com/pods-finance/yield-contracts/pull/41).
- C-2 in [pods-finance/yield-contracts#54](https://github.com/pods-finance/yield-contracts/pull/54).
- C-3 and H-3 in [pods-finance/yield-contracts#46](https://github.com/pods-finance/yield-contracts/pull/46).
- H-1 in [pods-finance/yield-contracts#73](https://github.com/pods-finance/yield-contracts/pull/73).

## Notes

The audit also lists Medium and Low findings. The task checks only the Criticals and Highs, and other true findings in the report don't fail it.
H-2 only hurts vaults built on the base contract, since the shipped stETH vault overrides `_deposit` in the right order.
It's a well-known 2022 report, so models may remember it.
The project's `audits/` folder holds an earlier CredShields report from July 2022 on an older commit. It lists no High or Critical finding, and it is the project's own file at the audited commit, so it stays.
The free check runs no judge. Its oracle run passes `report_written` with the solution's report, and its nop run fails it.
