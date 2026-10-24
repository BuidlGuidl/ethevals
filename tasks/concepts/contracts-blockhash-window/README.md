# BLOCKHASH after EIP-2935

The user asks whether BLOCKHASH can return a hash from 1,000 blocks back after Pectra.
The check requires no and the unchanged 256-block opcode window.

## The instruction

```text
After Pectra's EIP-2935, can a contract's BLOCKHASH opcode return the hash of a block 1,000 blocks back? Answer yes or no first, then one sentence.
```

## What it touches

EIP-2935 stores 8,191 historical hashes in a system contract.
It leaves BLOCKHASH limited to the previous 256 blocks; callers need the system contract for older hashes.

## The checks

| Check | What it proves | Area |
| --- | --- | --- |
| `blockhash_keeps_256_window` | Starts with no, states the 256-block window, and does not claim an 8,192-block history window | historical block hashes |

The quiz runs in vanilla, internet, and skills modes.

## Why it matters

Contracts that use BLOCKHASH for an older block receive zero even though the system contract retains its hash.
[EIP-2935](https://eips.ethereum.org/EIPS/eip-2935) separates the 256-block opcode window from the 8,191-block history contract.
