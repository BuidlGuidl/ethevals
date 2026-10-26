# Wallet atomic capability states

A dapp builder asks what separates the `supported` and `ready` states of EIP-5792's atomic capability.
`supported` means the wallet runs batches atomically now.
`ready` means it can upgrade to that, pending the user's approval, and the name reads the other way round.

## The instruction

> Under EIP-5792, a wallet's wallet_getCapabilities reports the atomic capability for a chain. What is the difference between status "supported" and status "ready"? Answer in one sentence.

## What it touches

EIP-5792 defines three states for the atomic capability:

| Status | Meaning |
| --- | --- |
| `supported` | the wallet will execute the calls atomically and contiguously |
| `ready` | the wallet can upgrade to `supported`, pending user approval |
| `unsupported` | no atomic guarantee, and the wallet won't suggest an upgrade |

An EIP-7702 account upgrade is one way a wallet gets from `ready` to `supported`, but EIP-5792 doesn't name a mechanism.
The common mistake swaps the first two, reading `ready` as "ready to batch now" and `supported` as "possible after setup".

## The checks

A judge reads the question, the right answer, and the final reply, and nothing else.
It passes the reply when it gives atomic execution now for `supported` and an upgrade for `ready`, in any wording, and fails swapped or hedged meanings.

| Check | What it proves | Area |
| --- | --- | --- |
| `answered` | The final reply isn't empty | reply |
| `supported_now_ready_upgrade` | The judge finds atomic execution now for supported, and an account upgrade for ready | wallet capability |

The quiz runs in vanilla, internet, and skills modes.

## Why it matters

An app that reads `ready` as "atomic now" plans for one step and gets something else:

- With `atomicRequired: true`, the wallet must upgrade first, so the user sees an upgrade prompt the app didn't plan for.
- With `atomicRequired: false`, the wallet may run the calls one by one, so an approval can land while the swap after it reverts.

An app that reads `supported` as "needs setup" sends separate transactions when one atomic batch was available.
[EIP-5792](https://eips.ethereum.org/EIPS/eip-5792) defines the states and these rules for `wallet_sendCalls`.

## Notes

The judge counts an EIP-7702 delegation, enabling, or activating the account as the upgrade, and it doesn't need approval wording.
It's the board's judge, Claude Opus 5.5 at high effort, and it never sees the model's reasoning ([ADR 0016](../../../docs/adr/0016-quizzes-with-explained-answers-use-a-judge.md)).
`tests/hand-cases.json` holds right and wrong replies with their correct marks, and the judge must give each one its mark.
