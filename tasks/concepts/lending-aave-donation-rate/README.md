# Aave donation and borrow rates

The user asks whether a direct USDC donation changes an Aave reserve's borrow rate.
The check requires no and a reason based on virtual accounting.

## The instruction

```text
On Aave v3.1 or later, someone transfers 1,000,000 USDC straight to the aUSDC contract without calling supply. Does the USDC reserve's borrow rate change? Answer yes or no first, then say why in one sentence.
```

## What it touches

Aave v3.1 uses an internal virtual balance to calculate available liquidity.
A transfer to the aToken contract bypasses that balance, so it changes neither utilization nor the borrow rate.

## The checks

| Check | What it proves | Area |
| --- | --- | --- |
| `donation_uses_virtual_balance` | Starts with no and identifies virtual accounting or internally tracked liquidity | reserve accounting |

The quiz runs in vanilla, internet, and skills modes.

## Why it matters

Apps that estimate borrow rates from the aToken's token balance can mistake donations for available liquidity.
[Aave's v3.1 release notes](https://github.com/aave-dao/aave-v3-origin/blob/v3.1.0/docs/Aave-v3.1-features.md) explain the virtual balance used by the rate strategy.
