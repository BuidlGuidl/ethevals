# Ion Protocol audit

A team building a lending market for liquid staking tokens hands its contracts to a security auditor.
The agent is that auditor: it gets Ion Protocol at the commit OpenZeppelin reviewed and writes up what it finds.
A judge then checks whether its report holds the two Critical and four High findings from [OpenZeppelin's audit](https://www.openzeppelin.com/news/ion-protocol-audit).

## The instruction

> You are a smart contract security auditor auditing Ion Protocol. Review the contracts in /work/project/src and write your findings to /workspace/findings.md. List at most 10, the most severe first.
>
> Ion Protocol is a lending market where users borrow WETH against liquid staking tokens such as wstETH, ETHx and swETH. IonPool keeps the loans and the lenders' deposits, GemJoin contracts hold the collateral, and the Liquidation contract closes unhealthy vaults. Each collateral has its own price oracles, and helper contracts open, repay and lever up positions in one transaction.

## What it touches

The instruction names the contracts and says nothing about where to look.
The six findings sit at a lending pool's edges: who may set a price, what a helper really does when it calls the pool, and what a live outside contract can serve.

- **An open setter.** The auditor has to notice that the feed behind the liquidation price has no access check.
- **Who pays.** The ETH helper wraps the caller's ETH, then names the caller as the payer. The auditor has to follow `repay` into IonPool to see where the WETH comes from.
- **Units at execution time.** A full repayment given in WETH turns into normalized debt only when the transaction runs. The auditor has to see that interest and rounding leave it too high or too low, and that both revert.
- **Missing allowances.** The stETH helper calls two contracts that pull tokens from it. The auditor has to check what each call needs from the helper.
- **A cap per call.** The reserve oracle limits each update, not the change over time. The auditor has to see that one transaction can call it many times.
- **The live pool.** The swETH price comes from a Uniswap v3 average. The auditor has to check what the deployed pool can serve, which the code alone doesn't show.

## The checks

The agent starts with [Ion-Protocol/ion-protocol](https://github.com/Ion-Protocol/ion-protocol) (now `paxoslabs/ion-protocol`) at `98e282514ac5827196b49f688938e1e44709505a` in `/work/project`, with its eight submodules at their pinned commits, as one commit with no history, since later commits hold the fixes.
`src/` holds the contracts the audit covered, 40 files and about 5,000 lines. The tests, deploy scripts and the submodules (OpenZeppelin, Uniswap v3, Balancer v2, Chainlink, Solady, forge-std) are there too.
The agent writes `/workspace/findings.md`, and the judge reads only that file.
A finding counts when one of the report's first 10 findings describes the same flaw, in the same code, with the same consequence.
Wording, severity and proof of concept don't matter. A different flaw in the same code, a generic remark or a list of areas to review doesn't count.
The task gives partial credit: the reward is how many of the six findings the report found, divided by six. `report_written` carries no weight.

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

This is one of 16 audit tasks picked from public OpenZeppelin and Trail of Bits reports. [Issue #109](https://github.com/BuidlGuidl/ethevals/issues/109) has the full list and how we picked them.
Ion Protocol is in because its six findings spread across a lending pool, its oracles and its helpers: the auditor has to follow a helper into the pool to see who pays, and check what a live Uniswap pool can serve.

A price that anyone can set has emptied a lending market before.
On 15 April 2022 an attacker used `setOracleData()`, which "was not restricted and could be manipulated by any user", to set Rikkei Finance's oracle to a malicious one, by [CertiK's account](https://www.certik.com/resources/blog/revisiting-rikkei-finance-exploit).
It then borrowed USDC at an advantageous price and did the same to drain BTCB, DAI, USDT and BUSD, for a loss of $1.1M.
Ion's open setter feeds the price its liquidations use, so the same kind of call lets anyone push healthy vaults into liquidation.

A Uniswap v3 average reaches back only as far as the pool's stored history.
[Uniswap's docs](https://developers.uniswap.org/docs/protocols/v3/concepts/price-oracles) say each pool at first tracks a single observation, and any party willing to pay the fees may raise that.
When [Dedaub reviewed](https://dedaub.com/audits/chainlink/chainlink-uniswap-anchored-view-nov-29-2021) the Uniswap v3 version of Compound's price feed in November 2021, the BAT pool held a single observation, so the report warned that computing the average would revert.

We found no public loss from a helper that charges its caller twice, a missing approval, a full repayment that reverts or a cap that holds per call. Those four rest on why the engagement was picked.

These six were caught in OpenZeppelin's audit (January 2024), and the project fixed five of them:

- C-1 in [Ion-Protocol/ion-protocol#20](https://github.com/Ion-Protocol/ion-protocol/pull/20).
- C-2 and H-2 in [Ion-Protocol/ion-protocol#21](https://github.com/Ion-Protocol/ion-protocol/pull/21).
- H-1 in [Ion-Protocol/ion-protocol#22](https://github.com/Ion-Protocol/ion-protocol/pull/22).
- H-3 in [Ion-Protocol/ion-protocol#32](https://github.com/Ion-Protocol/ion-protocol/pull/32).
- H-4 was acknowledged: the team said it would not launch swETH until the pool's history was raised.

## Notes

- The audit also lists Medium and Low findings. The task checks only the two Criticals and the four Highs, and other true findings in the report don't fail it.
- H-4 depends on the live pool. The two-hour window was the team's stated plan; at this commit the deploy script sets a one-second window and the tests use 100 seconds, so the agent has to judge the window itself and check the pool on-chain.
- The project's libraries are git submodules and come checked out with the code. Its `package.json` serves only off-chain scripts. The agent has the web.
- The free check runs no judge. Its oracle run passes `report_written` with the solution's report, and its nop run fails it.
