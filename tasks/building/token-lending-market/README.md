# Token lending market

A token team wants holders to borrow USDC without selling TKN, which larger markets will not list.
The task checks whether the market keeps its books correct when time passes, tokens arrive outside its functions, or collateral loses value.

## The instruction

> we want a small lending market for TKN (18 decimals). anyone lends USDC and earns the interest borrowers pay; the treasury takes 10% of that interest. holders borrow USDC against TKN up to 80% of its value; anyone can liquidate past that line by repaying USDC and taking TKN worth 5% more. the borrow rate climbs as more of the pool is lent out, pick a sensible curve. cap it at 2M USDC supplied and 1M TKN collateral. implement src/interfaces/IMarket.sol, using src/interfaces/IPriceFeed.sol, in src/Market.sol as Market, constructor (address usdc, address tkn, address priceFeed, address owner). foundry, solidity 0.8.30.

## What it touches

- Interest accounting. Idle time belongs to the utilization before the next action, and current balance views must include that interest.
- Booked assets. Plain token transfers cannot create supply or collateral, or consume room under a cap.
- Asset and share conversions. Dust must stay with the market across deposits, withdrawals, borrows, and repayments.
- Liquidation and losses. Excess repayment requests cannot block liquidation, and exhausted collateral requires a loss shared by lenders in that call.
- Treasury fees. The treasury receives a share of interest without taking principal or leaving a gap in the books.

## The checks

The agent starts with Foundry settings and two interfaces on Solidity 0.8.30, without a chain sidecar.
The verifier deploys its contract beside mock USDC with 6 decimals, TKN with 18 decimals, and a settable price feed.
Each test is one check, and every check must pass for a reward of 1.

| Check | What it proves | Area |
| --- | --- | --- |
| `compile` | The tests and the agent's contract compile together | all |
| `test_marketWorksAndBooksBalance` | Supply, borrow, repayment, and exits work; booked net assets never exceed cash, with at most five base units of extra cash; lenders receive 90% of interest and the treasury receives 10% | accounting |
| `test_interestChargedBeforeTheAction` | Views include idle interest, repayment charges it, and the next action cannot change the rate for past time | interest |
| `test_strayTokensChangeNothing` | Direct transfers change no balances or totals, and caps count booked supply and collateral | caps |
| `test_roundingFavoursMarket` | Repeated odd-amount cycles create no user profit, and a tiny debt remains owed and liquidatable | rounding |
| `test_liquidationFinishes` | Healthy loans resist liquidation, unhealthy loans pay the 5% incentive, excess requests clear debt, and distressed borrowers can repay or add collateral | liquidation |
| `test_badDebtWrittenOffAgainstLenders` | The liquidator pays only for the collateral and takes it all; equal lenders share the loss within five base units, both withdraw their full reported claims in either order, and the books balance | losses |

## Why it matters

[BiFi's idle-interest incident](https://sigintzero.com/blog/bifi-165k-idle-market-interest-accrual) shows why the next borrow cannot set the rate for past time.
[Cyfrin's Licredity audit](https://github.com/Cyfrin/cyfrin-audit-reports/blob/main/reports/2025-09-01-cyfrin-licredity-v2.0.pdf) found a repayment path that skipped accrual.
[Morpho SDK PR 886](https://github.com/morpho-org/sdks/pull/886) addresses repayments based on stored debt.

Donation-sensitive accounting appears in the [Venus THE](https://community.venus.io/t/the-market-incident-post-mortem/5712), [Moonwell MAMO](https://forum.moonwell.fi/t/post-mortem-mamo-market-incident-on-base/2208), and [Tectonic](https://rekt.news/tectonic-rekt) incident accounts.
Aave documents rounding changes in [v3.5](https://github.com/aave-dao/aave-v3-origin/blob/main/docs/3.5/Aave-v3.5-features.md) and [v3.7](https://github.com/aave-dao/aave-v3-origin/blob/main/docs/3.7/liquidation-rounding.md).
Small-debt errors also appear in the [Notional V1 account](https://blocksec.com/blog/web3-security-injective-aquifer-exploits) and [Zentra's statement](https://x.com/zentrafinance/status/2098415552293195831).

The [Notional Exponent finding](https://github.com/sherlock-audit/2025-06-notional-exponent-judging/issues/300) explains how excess-repayment reverts block liquidation.
[Trail of Bits' CAP Labs review](https://github.com/trailofbits/publications/blob/master/reviews/2025-05-caplabs-coveredagentprotocol-securityreview.pdf) describes losses that fall on the last lender to withdraw.
The [Moonwell MAMO withdrawal account](https://cryptoslate.com/lending-protocol-offers-bad-debt-fix-while-trapped-depositors-face-missing-usdc-funds-and-zero-cash-access/) describes what unowned debt means for lenders trying to leave.

## Notes

- The checks compare outcomes across paths and do not require a particular rate curve or share layout.
- Treasury interest can arrive as a supply claim or as USDC. The checks accept either form.
- Liquidation probes sit clearly inside and outside the 80% line, rather than depending on one unit of health rounding.
- Mock feeds can revert. Lender exits, repayments, and collateral additions require no collateral price.
- These six checks cover accounting habits. They do not constitute a contract audit or prove safety for arbitrary tokens.
