# Lender APY

Check whether a model applies utilization and fees before compounding lender interest.
The quiz checks one final reply against a fixed target.

## The instruction

```text
Our market charges borrowers a per-second rate that compounds every second, takes 10% of interest as a protocol fee, and runs at 80% utilization. Our page shows lenders an APY of borrower APY times 0.8 times 0.9. Is that number too high, too low, or exact? One phrase.
```

## What it touches

The target is too high.
Utilization and the lender's fee share scale the per-second rate before compounding.
Scaling the borrower's already compounded APY overstates the lender's APY.
The rule accepts high, overstated, or overestimate wording and rejects low or underestimate wording.

## The checks

| Check | What it proves | Area |
| --- | --- | --- |
| `lender_apy_too_high` | The reply identifies the displayed lender APY as too high | interest display |

The quiz runs in vanilla, internet, and skills modes.

## Why it matters

A lending page can overstate yield when it scales an annual compounded yield instead of the underlying rate.
[Morpho's interest accrual code](https://github.com/morpho-org/morpho-blue/blob/main/src/Morpho.sol) allocates borrower interest and protocol fees to supply assets and shares.
For the question's fixed per-second rate r, lender APY is (1 + r × 0.8 × 0.9)^N - 1, where N is seconds per year.
