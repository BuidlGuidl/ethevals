# Permit2 zero expiration

This quiz asks whether a spender can use a Permit2 approval with zero expiration in the next block.
The fixed answer is no, because zero sets the expiration to the approval block's timestamp.

## The instruction

```text
A script calls Uniswap's Permit2 approve(token, spender, amount, 0) for a spender. In the next block, the spender calls Permit2's transferFrom to pull those tokens. Does the pull succeed? Answer yes or no first, then say why in one sentence.
```

## What it touches

- Permit2 allowances. Zero expiration means the approval lasts for the current block. It does not mean an unlimited lifetime.
- Block timestamps. `approve` stores the current timestamp, and `transferFrom` rejects a later timestamp with `AllowanceExpired`.

## The checks

| Check | What it proves | Area |
| --- | --- | --- |
| `zero_expiration` | The reply starts with the word no, ignoring case and leading whitespace or punctuation | Permit2 allowances |

The check accepts Markdown around the first word and rejects words such as "not" and "nothing".
It checks the fixed answer, without judging the explanation.
The quiz runs in vanilla, internet, and skills modes.

## Why it matters

A swap script that treats zero expiration as unlimited can approve tokens successfully and still fail when the router spends them later.
The pinned [Allowance.sol constant](https://github.com/Uniswap/permit2/blob/cc56ad0f3439c502c246fc5cfcc3db92bb8b7219/src/libraries/Allowance.sol#L7-L8) and [approval update](https://github.com/Uniswap/permit2/blob/cc56ad0f3439c502c246fc5cfcc3db92bb8b7219/src/libraries/Allowance.sol#L39-L40) define zero as the current block's timestamp.
[AllowanceTransfer.sol](https://github.com/Uniswap/permit2/blob/cc56ad0f3439c502c246fc5cfcc3db92bb8b7219/src/AllowanceTransfer.sol#L77-L83) rejects a transfer when `block.timestamp > allowed.expiration`.
