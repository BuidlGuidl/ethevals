# Arbitrum governance block clock

The user asks how long 50,400 clock ticks keep an Arbitrum One vote open.
The check requires about seven days.

## The instruction

```text
A Governor on Arbitrum One uses block.number as its clock, with votingPeriod = 50,400. About how long does a vote stay open? Answer with the duration first, then one sentence.
```

## What it touches

On Arbitrum One, Solidity's block.number approximates the Ethereum L1 block number.
It does not count Arbitrum's faster L2 blocks, so 50,400 ticks take about seven days.

## The checks

| Check | What it proves | Area |
| --- | --- | --- |
| `l1_clock_seven_days` | Starts with about seven days or an equivalent duration | governance clock |

The quiz runs in vanilla, internet, and skills modes.

## Why it matters

A Governor with the wrong clock assumption can close votes hours before token holders expect.
[Arbitrum's block number documentation](https://docs.arbitrum.io/build-decentralized-apps/arbitrum-vs-ethereum/block-numbers-and-time) distinguishes the Solidity clock from the L2 block count.
