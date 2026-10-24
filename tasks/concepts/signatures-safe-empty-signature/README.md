# Safe empty signatures

The question asks when Safe v1.4.1 accepts an empty signature through its standard fallback handler.
The check distinguishes onchain message approval from owner signature checks.

## The instruction

```text
A Safe smart account (v1.4.1, standard fallback handler) is asked isValidSignature(hash, signature) with an empty signature. When does it return the ERC-1271 magic value? Answer in one short phrase first, then one sentence.
```

## What it touches

The [CompatibilityFallbackHandler](https://github.com/safe-global/safe-smart-account/blob/v1.4.1/contracts/handler/CompatibilityFallbackHandler.sol) wraps the supplied hash in a Safe-specific `SafeMessage` hash.
For an empty signature, it requires a nonzero entry for that message in the Safe's `signedMessages` mapping.
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
