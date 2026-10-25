# Wallet atomic capability states

A dapp builder asks what separates the `supported` and `ready` states of EIP-5792's atomic capability.
`supported` means the wallet runs batches atomically now.
`ready` means it can upgrade to that, pending the user's approval, and the name reads the other way round.

## The instruction

```text
Under EIP-5792, a wallet's wallet_getCapabilities reports the atomic capability for a chain. What is the difference between status "supported" and status "ready"? Answer in one sentence.
```

## What it touches

EIP-5792 defines three states for the atomic capability:

```text
supported:    the wallet will execute the calls atomically and contiguously
ready:        the wallet can upgrade to supported, pending user approval
unsupported:  no atomic guarantee, and the wallet won't suggest an upgrade
```

An EIP-7702 account upgrade is one way a wallet gets from `ready` to `supported`, but EIP-5792 doesn't name a mechanism.
The common mistake swaps the first two, reading `ready` as "ready to batch now" and `supported` as "possible after setup".

## The checks

The rule reads what the reply says about each state.
It needs atomic execution for `supported` and an upgrade for `ready`, and it refuses the swapped meanings.

| Check | What it proves | Area |
| --- | --- | --- |
| `supported_now_ready_upgrade` | Assigns atomic execution to supported and an account upgrade to ready | wallet capability |

The quiz runs in vanilla, internet, and skills modes.

## Why it matters

An app that reads `ready` as "atomic now" plans for one step and gets something else.
With `atomicRequired: true`, the wallet must upgrade first, so the user sees an upgrade prompt the app didn't plan for.
With `atomicRequired: false`, the wallet may run the calls one by one, so an approval can land while the swap after it reverts.
An app that reads `supported` as "needs setup" sends separate transactions when one atomic batch was available.
[EIP-5792](https://eips.ethereum.org/EIPS/eip-5792) defines the states and these rules for `wallet_sendCalls`.

## Notes

The rule accepts either state first, and it ignores Markdown or a leading "Short answer:".
It refuses a `supported` clause that says "not" or "cannot", or that execution needs setup or an upgrade.
It needs upgrade wording for `ready`, but not approval wording or a named upgrade mechanism.
