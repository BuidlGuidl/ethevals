# Aave small position close factor

A liquidation bot builder asks how much of a $1,500 USDC debt one call can repay at a health factor of 0.98.
The answer is 100%, all $1,500.
The 50% cap most builders remember stopped applying to small positions in Aave v3.3.

## The instruction

```text
On Aave v3.3, a position has a health factor of 0.98, with $1,500 of USDC debt and about $1,770 of WETH collateral. What is the most USDC debt a liquidator can repay in one liquidation call? Answer with a percentage of the debt first, then one sentence.
```

## What it touches

A close factor limits how much of a borrower's debt one liquidation can repay.
Before v3.3, any position with a health factor above 0.95 had a 50% cap.
Aave v3.3 keeps that cap only for larger positions.
The user's debt and collateral in the two reserves of the call must both be at least $2,000.
This debt is $1,500, so one call can repay all of it.

```text
debt >= $2,000, collateral >= $2,000, health factor > 0.95:   50% cap
anything else:                                                up to 100%

this position: $1,500 debt, about $1,770 collateral, 0.98:    up to 100%
```

Aave v3.3 also rules out the 50% answer directly.
A partial liquidation must leave at least $1,000 of debt and $1,000 of collateral in those reserves.
Repaying $750 here would leave $750 of debt, so that call reverts with `MUST_NOT_LEAVE_DUST`.

## The checks

The check reads the percentage at the start of the reply.
It needs 100%, and a reply that opens with 50% fails even if a later sentence corrects it.

| Check | What it proves | Area |
| --- | --- | --- |
| `small_position_full_close` | Starts with 100% or one hundred percent | liquidation |

The quiz runs in vanilla, internet, and skills modes.

## Why it matters

A bot that sizes every liquidation at 50% sends a call that reverts on positions like this one, so small debts stay open.
Aave added the rule because small positions cut in half become dust that nobody can liquidate at a profit.
The [v3.3 release notes](https://github.com/aave-dao/aave-v3-origin/blob/v3.3.0/docs/3.3/Aave-v3.3-features.md) say "most of these dust debt positions are caused by the 50% close factor being applied to already small positions".
[LiquidationLogic at v3.3.0](https://github.com/aave-dao/aave-v3-origin/blob/v3.3.0/src/contracts/protocol/libraries/logic/LiquidationLogic.sol#L74-L82) sets the $2,000 and $1,000 thresholds, and [its dust check](https://github.com/aave-dao/aave-v3-origin/blob/v3.3.0/src/contracts/protocol/libraries/logic/LiquidationLogic.sol#L320-L343) reverts the half-size call.

## Notes

The check accepts `100%`, `100 percent`, or `one hundred percent`, including Markdown and a leading "Short answer:".
It refuses a dollar amount alone and does not check the explanation after the percentage.

The $2,000 test uses the user's balance in each reserve in the call, not their position totals.
The constant's NatSpec says "position", but the code and the release notes say reserve.

With WETH's real liquidation threshold, these amounts give a health factor near 0.89, which would allow 100% on its own.
The question states 0.98, so the answer rests on the size rule.
