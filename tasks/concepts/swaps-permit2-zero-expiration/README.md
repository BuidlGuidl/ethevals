# Permit2 zero expiration

A swap frontend builder asks when a Permit2 allowance set with `approve(..., expiration = 0)` expires.
Permit2 replaces the 0 with the current `block.timestamp`, so the allowance lasts for that block only.
Many APIs use 0 to mean "no expiry", which makes "never expires" the tempting answer.

## The instruction

> A user calls Permit2's approve(token, spender, amount, expiration) with expiration = 0. When does that allowance expire? Answer in one short phrase first, then one sentence.

## What it touches

Permit2 stores `block.timestamp` when the expiration passed in is 0.
Its transfer check reverts only when `block.timestamp > expiration`, so a transfer in the same block still works.

```text
block N:      approve(..., expiration = 0) stores block N's timestamp
block N:      transferFrom uses the allowance
block N + 1:  transferFrom reverts with AllowanceExpired
```

There are two wrong readings.
"Never expires" misses that Permit2 swaps the 0 for the timestamp.
"Already expired" or "unusable" misses that the check is a strict greater-than, so the approving block can still spend it.

## The checks

The check reads the first sentence of the reply.
It needs the current block or its timestamp there, and it refuses a reply that says the allowance never expires or can't be used.

| Check | What it proves | Area |
| --- | --- | --- |
| `expires_at_current_block` | Names the current block or its timestamp as the expiration in the first sentence | allowance lifetime |

The quiz runs in vanilla, internet, and skills modes.

## Why it matters

A frontend that passes 0 to mean "no expiry" gives the user an allowance that ends with the block.
The approve transaction succeeds, and the user's swap in a later block reverts with `AllowanceExpired`.
[Permit2's allowance library](https://github.com/Uniswap/permit2/blob/main/src/libraries/Allowance.sol#L39) stores the timestamp, and its [transfer check](https://github.com/Uniswap/permit2/blob/main/src/AllowanceTransfer.sol#L79) enforces it.

## Notes

The check accepts `block.timestamp`, "current block", "same block", or "end of the block" anywhere in the first sentence.
It refuses phrases such as "never expires", "already expired", or "unusable" anywhere in the reply, even in a denial.
It does not run a transfer or check other allowance conditions.

On a mainnet fork, `approve` with expiration 0 stored exactly that block's timestamp.
