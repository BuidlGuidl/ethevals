# A feed that reverts

Check whether a model distinguishes a lender withdrawal from a liquidation that needs an oracle price.
The quiz checks one final reply against a fixed target.

## The instruction

```text
Our market's price feed reverts on every call. For a lender with no debt, which still works: withdrawing their supply, liquidating a borrower, both, or neither?
```

## What it touches

The target is withdrawing.
A lender with no debt needs no collateral valuation to withdraw supply.
Liquidation needs the feed to price a borrower's collateral.
The rule accepts replies that start with withdraw, withdrawing, or withdrawal after trimming spaces and punctuation.

## The checks

| Check | What it proves | Area |
| --- | --- | --- |
| `withdraw_without_price` | The reply selects withdrawing supply | oracle dependencies |

The quiz runs in vanilla, internet, and skills modes.

## Why it matters

A broken feed can stop liquidations while a debt-free lender's withdrawal still needs no price.
[Morpho's withdrawal and liquidation code](https://github.com/morpho-org/morpho-blue/blob/main/src/Morpho.sol) shows these distinct dependencies.
