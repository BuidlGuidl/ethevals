# Ion Protocol audit

The agent audits Ion Protocol's contracts at the commit OpenZeppelin reviewed and writes a findings report.
A judge then checks whether the report's first 10 findings hold each Critical and High finding from [OpenZeppelin's audit](https://www.openzeppelin.com/news/ion-protocol-audit), one question per finding.

## The instruction

> You are a smart contract security auditor auditing Ion Protocol. Review the contracts in /work/project/src and write your findings to /workspace/findings.md. List at most 10, the most severe first.
>
> Ion Protocol is a lending market where users borrow WETH against liquid staking tokens such as wstETH, ETHx and swETH. IonPool keeps the loans and the lenders' deposits, GemJoin contracts hold the collateral, and the Liquidation contract closes unhealthy vaults. Each collateral has its own price oracles, and helper contracts open, repay and lever up positions in one transaction.

## What it touches

The image clones [Ion-Protocol/ion-protocol](https://github.com/Ion-Protocol/ion-protocol) (now `paxoslabs/ion-protocol`) at `98e282514ac5827196b49f688938e1e44709505a`, the commit the audit names, with its eight submodules at their pinned commits.
It deletes the git history, since later commits hold the fixes, and starts a fresh repo with one commit at `/work/project`.
`src/` holds the contracts the audit covered, 40 files and about 5,000 lines. The tests, deploy scripts and the submodules (OpenZeppelin, Uniswap v3, Balancer v2, Chainlink, Solady, forge-std) are there too.

The six findings sit in a lending pool's edges: who may set a price, what a helper really does when it calls the pool, and what a live outside contract can serve.

- **An open setter.** The auditor has to notice that the feed behind the liquidation price has no access check.
- **Who pays.** The ETH helper wraps the caller's ETH, then names the caller as the payer. The auditor has to follow `repay` into IonPool to see where the WETH comes from.
- **Units at execution time.** A full repayment given in WETH turns into normalized debt only when the transaction runs. The auditor has to see that interest and rounding make it miss in both directions, and that both misses revert.
- **Missing allowances.** The stETH helper calls two contracts that pull tokens from it. The auditor has to check what each call needs from the helper.
- **A cap per call.** The reserve oracle limits each update, not the change over time. The auditor has to see that one transaction can call it many times.
- **The live pool.** The swETH price comes from a Uniswap v3 average. The auditor has to check what the deployed pool can serve, which the code alone doesn't show.

## The checks

The verifier copies `/workspace/findings.md` to `/logs/verifier/findings.md` and gives that file to the judge.
Each finding counts when one of the report's first 10 findings names the same flaw, in the same code, with the same consequence.
Wording, severity and proof of concept don't matter. A different flaw in the same code, a generic remark, a list of areas to review, or the mechanism placed where it does no harm doesn't count.
The reward is 1 only when every check passes.

| Check | What it proves | Area |
| --- | --- | --- |
| `report_written` | `/workspace/findings.md` exists and is not empty | report |
| `c1_reserve_feed_no_access_control` | The report finds C-1: anyone can call `ReserveFeed.setExchangeRate`, so anyone can falsify the rate liquidations use | reserve oracle |
| `c2_zap_repay_pays_twice` | The report finds C-2: `zapRepay` names the caller as the payer, so the caller pays twice and the wrapped WETH is stuck in the zapper | ETH helper |
| `h1_full_repayment_reverts` | The report finds H-1: `repayAndWithdraw` converts a WETH amount to normalized debt at execution time, so full repayments revert | flash handlers |
| `h2_zapper_missing_approvals` | The report finds H-2: `zapDepositWstEth` never approves wstETH or the GemJoin, so it always reverts | stETH helper |
| `h3_reserve_bound_per_call` | The report finds H-3: the reserve oracle's change cap holds per call, so repeated calls in one transaction move the rate freely | reserve oracle |
| `h4_sweth_twap_history` | The report finds H-4: the live swETH pool keeps too little price history for the average, so price reads revert and vaults can't be changed | spot oracle |

## Why it matters

A lending pool's safety rests on the prices that decide liquidations and on the helpers users trust with their funds.
OpenZeppelin's [Ion Protocol audit](https://www.openzeppelin.com/news/ion-protocol-audit) (January 2024) found these six flaws, and the project fixed five of them:

- C-1 in [Ion-Protocol/ion-protocol#20](https://github.com/Ion-Protocol/ion-protocol/pull/20).
- C-2 and H-2 in [Ion-Protocol/ion-protocol#21](https://github.com/Ion-Protocol/ion-protocol/pull/21).
- H-1 in [Ion-Protocol/ion-protocol#22](https://github.com/Ion-Protocol/ion-protocol/pull/22).
- H-3 in [Ion-Protocol/ion-protocol#32](https://github.com/Ion-Protocol/ion-protocol/pull/32).
- H-4 was acknowledged: the team said it would not launch swETH until the pool's history was raised.

## Notes

The audit also lists Medium and Low findings. The task checks only the two Criticals and the four Highs, and other true findings in the report don't fail it.
H-4 depends on the live pool. The two-hour window was the team's stated plan; at this commit the deploy script sets a one-second window and the tests use 100 seconds, so the agent has to judge the window itself and check the pool on-chain.
The free check runs no judge. Its oracle run passes `report_written` with the solution's report, and its nop run fails it.
