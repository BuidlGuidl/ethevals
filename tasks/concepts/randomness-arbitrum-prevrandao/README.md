# Arbitrum prevrandao

A dice game builder who mixes `block.prevrandao` into the seed asks what it returns inside a contract on Arbitrum One.
The constant 1.
A model that assumes L2s mirror Ethereum's RANDAO answers with a beacon chain value.

## The instruction

> A contract on Arbitrum One reads block.prevrandao. What value does it get? Answer with the value, then explain in one sentence.

## What it touches

On Ethereum, `block.prevrandao` is the beacon chain's RANDAO mix, known one slot ahead and biasable by one bit per proposer.
Arbitrum One has no RANDAO. Its Solidity support page lists `block.prevrandao` and `block.difficulty` as returning the constant 1.
A seed that mixes it in gains nothing, and a game that relies on it is fully predictable.

| Chain | `block.prevrandao` |
| --- | --- |
| Ethereum mainnet | the slot's RANDAO mix |
| Arbitrum One | 1 |

## The checks

The check reads the first number in the reply and needs it to be 1.

| Check | What it proves | Area |
| --- | --- | --- |
| `prevrandao_is_one` | The first number given is 1 | block fields on L2s |

The quiz runs in vanilla, internet, and skills modes.

## Why it matters

Randomness code is copied between chains.
A contract that mixes `block.prevrandao` into its seed on Arbitrum ships a constant, and anything derived from it can be computed in advance.
Arbitrum's [Solidity support page](https://docs.arbitrum.io/build-decentralized-apps/arbitrum-vs-ethereum/solidity-support) lists the value, and [EIP-4399](https://eips.ethereum.org/EIPS/eip-4399) describes what the field means on Ethereum.

## Notes

The check takes the first decimal or hexadecimal number in the reply, so "the constant 1" and "0x1" pass and "the L1 RANDAO value" fails for having no number.
A reply that gives another number first fails even if 1 appears later.
The instruction names no game: a first wording that opened with "our dice game mixes block.prevrandao into its seed" came back from the API with no text in two trials, because a refusal classifier read it as tampering with game randomness, so the dice game stays here and the instruction asks the bare question.
