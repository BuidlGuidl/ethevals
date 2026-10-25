# Safe empty signatures

The question asks a builder adding ERC-1271 sign-in when a normal Safe accepts an empty signature.
The check distinguishes onchain message approval from owner signature checks.

## The instruction

> We're adding ERC-1271 checks so Safe users can sign in. If we call isValidSignature(hash, 0x) on a normal Safe with an empty signature, when, if ever, does it return the magic value? Answer in one short phrase first, then one sentence.

## What it touches

A normal Safe is one with the default [CompatibilityFallbackHandler](https://github.com/safe-global/safe-smart-account/blob/v1.4.1/contracts/handler/CompatibilityFallbackHandler.sol), which the Safe app installs.
The handler wraps the supplied hash in a Safe-specific `SafeMessage` hash.
For an empty signature, it requires a nonzero entry for that message in the Safe's `signedMessages` mapping.
The handler does the same at [v1.3.0](https://github.com/safe-global/safe-smart-account/blob/v1.3.0/contracts/handler/CompatibilityFallbackHandler.sol#L32-L33), v1.4.1 and [v1.5.0](https://github.com/safe-global/safe-smart-account/blob/v1.5.0/contracts/handler/CompatibilityFallbackHandler.sol#L78-L79).

[SignMessageLib](https://github.com/safe-global/safe-smart-account/blob/v1.4.1/contracts/libraries/SignMessageLib.sol#L19-L22) records that approval through `signMessage` in the Safe's storage.
Owner-level `approvedHashes` entries alone do not satisfy this branch.

## The checks

| Check | What it proves | Area |
| --- | --- | --- |
| `safe_message_approved` | The first two sentences name prior or onchain Safe message approval, including signedMessages or SignMessageLib | Safe and ERC-1271 |

The check rejects an uninitialized Safe, never, always, and owner approval alone as the opening answer.
The quiz runs in vanilla, internet, and skills modes through a separate RewardKit verifier.

## Why it matters

Safe message approval lets applications accept a message without collecting signature bytes in the request.
[Snapshot's relayer](https://github.com/snapshot-labs/snapshot-relayer/blob/ed7f18a/src/check.ts#L95-L130) waits for `signedMessages` before it forwards pending Safe messages.
Treating every empty signature as invalid blocks this approval flow.
