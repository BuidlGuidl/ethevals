# Transaction gas cap

A raffle builder who settles every buyer in one transaction asks how much gas one mainnet transaction can use at most.
16,777,216 gas, which is 2^24, since the Fusaka upgrade.
A model that learned mainnet before Fusaka answers with the block gas limit, because no per-transaction cap existed.

## The instruction

> Our raffle settles by looping over every buyer in one transaction. What is the most gas a single transaction can use on Ethereum mainnet today? Answer with the number.

## What it touches

Before Fusaka, one transaction could use the whole block gas limit.
EIP-7825 caps a single transaction at 16,777,216 gas. A transaction asking for more is invalid: nodes drop it from the pool and reject blocks that include it.

| When | Most gas in one transaction |
| --- | --- |
| Before Fusaka | the block gas limit, tens of millions |
| Since Fusaka | 16,777,216 |

A loop that pays out thousands of users in one call can no longer be mined, however high the block limit goes.

## The checks

The check needs 16,777,216 in the reply, with or without separators, or 2^24.

| Check | What it proves | Area |
| --- | --- | --- |
| `transaction_gas_cap` | Gives 16,777,216 or 2^24 | transaction limits |

The quiz runs in vanilla, internet, and skills modes.

## Why it matters

Settlement loops, airdrops and mass refunds are sized against this cap, not the block limit.
[EIP-7825](https://eips.ethereum.org/EIPS/eip-7825) sets the value and how clients treat a transaction above it, and [Fusaka's meta EIP](https://eips.ethereum.org/EIPS/eip-7607) lists it among the upgrade's EIPs.
Fusaka activated on mainnet on 2025-12-03.

## Notes

The check accepts the number with commas, underscores or spaces, and the power-of-two forms `2^24` and `2**24`.
It does not refuse a reply that also mentions the block gas limit.
