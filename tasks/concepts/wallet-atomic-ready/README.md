# Wallet atomic capability states

The user asks how the supported and ready atomic capability states differ.
The check requires present atomic execution for supported and a user-approved upgrade for ready.

## The instruction

```text
Under EIP-5792, a wallet's wallet_getCapabilities reports the atomic capability for a chain. What is the difference between status "supported" and status "ready"? Answer in one sentence.
```

## What it touches

EIP-5792 uses supported for wallets that execute calls atomically and contiguously.
Ready means that the wallet can upgrade to supported after the user approves.

## The checks

| Check | What it proves | Area |
| --- | --- | --- |
| `supported_now_ready_upgrade` | Assigns current atomic execution to supported and a user-approved upgrade to ready | wallet capability |

The quiz runs in vanilla, internet, and skills modes.

## Why it matters

Dapps need this distinction to know when to ask for an account upgrade before sending an atomic batch.
[EIP-5792](https://eips.ethereum.org/EIPS/eip-5792) defines ready as an upgrade path that needs user approval.
