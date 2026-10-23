# Idle interest

Check whether a model accrues idle interest before a borrow changes utilization.
The quiz checks one final reply against a fixed target.

## The instruction

```text
Our market's rate depends on utilization. Nobody has touched it for 30 days. A user then borrows enough to double the utilization. Are the 30 days charged at the utilization before the borrow or after? One word.
```

## What it touches

The target is before.
The elapsed period uses the utilization that held during that period.
The new borrow changes utilization only for later interest.
The rule accepts before at the start of the reply after trimming spaces and punctuation.

## The checks

| Check | What it proves | Area |
| --- | --- | --- |
| `pre_borrow_utilization` | The reply selects utilization before the borrow | interest accrual |

The quiz runs in vanilla, internet, and skills modes.

## Why it matters

Changing utilization before charging elapsed interest can charge the old debt at a newly raised rate.
The design document cites the [BiFi idle-interest incident](https://sigintzero.com/blog/bifi-165k-idle-market-interest-accrual) as this failure.
