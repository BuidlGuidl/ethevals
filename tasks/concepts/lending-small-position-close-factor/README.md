# Aave small position close factor

The user asks how much of a small USDC debt a liquidator can repay in one call.
The check requires the 100% close factor introduced for small balances in Aave v3.3.

## The instruction

```text
On Aave v3.3, a position has a health factor of 0.98, with $1,500 of USDC debt and about $1,770 of WETH collateral. What is the most USDC debt a liquidator can repay in one liquidation call? Answer with a percentage of the debt first, then one sentence.
```

## What it touches

Aave v3.3 allows a 100% close factor when the debt or collateral in the chosen reserves is below $2,000.
A health factor above 0.95 does not impose the usual 50% cap on these small balances.

## The checks

| Check | What it proves | Area |
| --- | --- | --- |
| `small_position_full_close` | Starts with 100% or one hundred percent | liquidation |

The quiz runs in vanilla, internet, and skills modes.

## Why it matters

Liquidation tools need the right close factor to size a repayment and estimate collateral proceeds.
[Aave's v3.3 liquidation logic](https://github.com/aave-dao/aave-v3-origin/blob/v3.3.0/src/contracts/protocol/libraries/logic/LiquidationLogic.sol) applies the small-balance threshold before the 50% cap.
