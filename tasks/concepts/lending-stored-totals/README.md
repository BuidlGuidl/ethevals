# Stored debt totals

Check whether a model includes pending interest when reading debt from stored market totals.
The quiz checks one final reply against a fixed target.

## The instruction

```text
Our borrow page computes what a user owes from the market's stored total debt and total debt shares, which the contract updates only when someone transacts. The market has been quiet for a day. Is the number our page shows too high, too low, or exact? One phrase.
```

## What it touches

The target is too low.
Stored totals omit interest since the last transaction.
A page must account for that pending interest before converting debt shares into the amount owed.
The rule accepts low, understated, or underestimate wording and rejects high or overestimate wording.

## The checks

| Check | What it proves | Area |
| --- | --- | --- |
| `stored_debt_too_low` | The reply identifies debt from stored totals as too low | debt display |

The quiz runs in vanilla, internet, and skills modes.

## Why it matters

A stale debt estimate can leave debt unpaid or cause a repayment to revert when the contract accrues interest.
[Morpho SDK PR #886](https://github.com/morpho-org/sdks/pull/886) changes repayment calculations to accrue interest forward.
