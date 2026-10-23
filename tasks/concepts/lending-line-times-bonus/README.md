# Line times bonus

Check whether a model includes the liquidation bonus when assessing debt coverage.
The quiz checks one final reply against a fixed target.

## The instruction

```text
Our market liquidates once debt passes 95% of the collateral's value and pays the liquidator 10% more collateral than they repay. How far can the price fall after a loan crosses the line before a full liquidation leaves debt that no collateral covers? Give a percentage.
```

## What it touches

The target is 0%.
At the liquidation line, repaying 95 requires collateral worth 104.5 after the 10% bonus, but the borrower holds 100.
The rule accepts a first number of zero, including decimal forms.
Without a number, it accepts zero, none, or already wording.

## The checks

| Check | What it proves | Area |
| --- | --- | --- |
| `no_price_margin` | The reply gives zero remaining price margin | liquidation |

The quiz runs in vanilla, internet, and skills modes.

## Why it matters

The liquidation line and bonus together decide whether collateral covers a full repayment.
[Morpho's liquidation documentation](https://docs.morpho.org/learn/concepts/liquidation/) explains the incentive and the line-times-incentive limit.
