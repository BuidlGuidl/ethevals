# Wallet batch status 600

The user asks what wallet_getCallsStatus status 600 means.
The check requires a partial revert or failure.

## The instruction

```text
Under EIP-5792, wallet_getCallsStatus returns status 600 for a batch of calls. What does that mean? Answer in one short phrase first, then one sentence.
```

## What it touches

EIP-5792 status 600 means that the batch reverted partially.
Some calls can leave changes onchain even though other calls reverted.

## The checks

| Check | What it proves | Area |
| --- | --- | --- |
| `partial_onchain_revert` | Starts with a partial revert or failure, or describes mixed call outcomes first | wallet batch status |

The quiz runs in vanilla, internet, and skills modes.

## Why it matters

A dapp that treats partial failure as a complete rollback can repeat calls that already changed state.
[EIP-5792](https://eips.ethereum.org/EIPS/eip-5792) defines status 600 and warns that some changes can remain onchain.
