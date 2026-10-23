# Leftover debt

Check whether a model knows who bears debt that stays on the books after collateral runs out.
The quiz checks one final reply against a fixed target.

## The instruction

```text
A liquidation takes all of a borrower's collateral and 1,000 USDC of debt stays on the books. If the market does nothing more, who bears the loss: every lender now, the last lenders to leave, or nobody? One phrase.
```

## What it touches

The target is the last lenders to leave.
Debt that stays in the totals keeps the stated value of lender shares above the cash available for withdrawal.
Earlier lenders can withdraw that stated value and leave the shortfall for the last lenders.
The rule accepts last-lender or last-withdrawer phrasing and rejects a claim that every lender shares the loss now.

## The checks

| Check | What it proves | Area |
| --- | --- | --- |
| `loss_falls_on` | The reply names the last lenders and rejects sharing the loss now | bad debt |

The quiz runs in vanilla, internet, and skills modes.

## Why it matters

Keeping uncollectible debt on the books lets earlier lenders withdraw before the market recognizes the loss.
[Trail of Bits' CAP Labs review](https://github.com/trailofbits/publications/blob/master/reviews/2025-05-caplabs-coveredagentprotocol-securityreview.pdf) describes this last-withdrawer problem.
