# Permit2 zero expiration

The user asks when a Permit2 allowance expires if approve receives expiration zero.
The check requires the current block's timestamp or the end of that block.

## The instruction

```text
A user calls Permit2's approve(token, spender, amount, expiration) with expiration = 0. When does that allowance expire? Answer in one short phrase first, then one sentence.
```

## What it touches

Permit2 replaces expiration zero with block.timestamp when it stores the allowance.
The spender can use it in that block, since the transfer check rejects timestamps strictly after expiration.

## The checks

| Check | What it proves | Area |
| --- | --- | --- |
| `expires_at_current_block` | Starts with the current block or its timestamp as the expiration | allowance lifetime |

The quiz runs in vanilla, internet, and skills modes.

## Why it matters

An app that treats zero as unlimited can leave a spender with an allowance that expires before the next block.
[Permit2's allowance library](https://github.com/Uniswap/permit2/blob/main/src/libraries/Allowance.sol) handles zero as a current-block expiration.
