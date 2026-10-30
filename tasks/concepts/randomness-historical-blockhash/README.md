# Historical block hash on mainnet

A contract builder asks whether a mainnet contract can read the hash of a block 1,000 blocks back, and from where.
Yes, since the Pectra upgrade. The EIP-2935 history contract at `0x0000F90827F1C53a10cb7A02335B175320002935` serves the last 8,191 block hashes.
A model that learned the 256-block limit of `BLOCKHASH` answers no.

## The instruction

> A contract on Ethereum mainnet needs the hash of a block 1,000 blocks back. Can it read that hash on chain today, and if so from which address? Answer yes or no, then give the address.

## What it touches

`BLOCKHASH` still returns zero for anything older than 256 blocks; EIP-2935 did not change the opcode.
It added a system contract that keeps a ring buffer of the last 8,191 block hashes.
A contract calls it with the 32-byte block number as calldata and gets the hash back, or a revert outside the window.

| How | Reach |
| --- | --- |
| `blockhash(n)` | last 256 blocks |
| call `0x0000F90827F1C53a10cb7A02335B175320002935` with `n` | last 8,191 blocks |

Pectra activated on mainnet on 2025-05-07.

## The checks

The check needs a yes at the start of the reply and the history contract as the first hexadecimal address.
It refuses no, and it refuses a different first address.

| Check | What it proves | Area |
| --- | --- | --- |
| `history_contract_address` | Starts with yes and names 0x0000F90827F1C53a10cb7A02335B175320002935 first | block history |

The quiz runs in vanilla, internet, and skills modes.

## Why it matters

Games that roll at a future block, bridges and light clients that prove old headers, and anything that reads `blockhash` late used to break after 256 blocks.
[EIP-2935](https://eips.ethereum.org/EIPS/eip-2935) defines the contract, its address and the 8,191-block window, and [Pectra's meta EIP](https://eips.ethereum.org/EIPS/eip-7600) records its activation.

## Notes

The check compares the address numerically, so any letter case passes.
It does not ask for the window size or the calldata format.
"Today" in the question means after Pectra. Before 2025-05-07 the right answer was no.
