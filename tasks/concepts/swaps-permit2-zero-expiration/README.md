# Permit2 zero expiration

A swap frontend builder asks when a Permit2 allowance set with `approve(..., expiration = 0)` expires.
Permit2 replaces the 0 with the current `block.timestamp`, so the allowance lasts for that block only.
Many APIs use 0 to mean "no expiry", which makes "never expires" the tempting answer.

## The instruction

> A user calls Permit2's approve(token, spender, amount, expiration) with expiration = 0. When does that allowance expire? Answer in one short phrase first, then one sentence.

## What it touches

Permit2 stores `block.timestamp` when the expiration passed in is 0.
Its transfer check reverts only when `block.timestamp > expiration`, so a transfer in the same block still works.

| Block | Call | Result |
| --- | --- | --- |
| N | `approve(..., expiration = 0)` | stores block N's timestamp as the expiration |
| N | `transferFrom` | spends the allowance |
| N + 1 | `transferFrom` | reverts with `AllowanceExpired` |

There are two wrong readings:

- "Never expires" misses that Permit2 swaps the 0 for the timestamp.
- "Already expired" or "unusable" misses that the check is a strict greater-than, so the approving block can still spend it.

## The checks

A judge reads the question, the right answer, and the final reply, and nothing else.
It passes the reply when it says the allowance expires at the current block's timestamp or lasts only for that block, in any wording, and fails a reply that hedges.

| Check | What it proves | Area |
| --- | --- | --- |
| `answered` | The final reply isn't empty | reply |
| `expires_at_current_block` | The judge finds the current block's timestamp, or that block only, as the expiration | allowance lifetime |

The quiz runs in vanilla, internet, and skills modes.

## Why it matters

A frontend that passes 0 to mean "no expiry" gives the user an allowance that ends with the block.
The approve transaction succeeds, and the user's swap in a later block reverts with `AllowanceExpired`.
[Permit2's allowance library](https://github.com/Uniswap/permit2/blob/cc56ad0f3439c502c246fc5cfcc3db92bb8b7219/src/libraries/Allowance.sol#L39-L40) stores the timestamp, and its [transfer check](https://github.com/Uniswap/permit2/blob/cc56ad0f3439c502c246fc5cfcc3db92bb8b7219/src/AllowanceTransfer.sol#L79) enforces it.

## Notes

The judge fails a reply that says the allowance never expires, is unusable even in its own block, expires at Unix time 0 or after a default period, or that the call reverts.
It's the board's judge, Claude Opus 5.5 at high effort, and it never sees the model's reasoning ([ADR 0016](../../../docs/adr/0016-quizzes-with-explained-answers-use-a-judge.md)).
`tests/hand-cases.json` holds right and wrong replies with their correct marks, and the judge must give each one its mark.

On a mainnet fork, `approve` with expiration 0 stored exactly that block's timestamp.
