# EntryPoint v0.8 UserOperation hash

The user asks how EntryPoint v0.8 computes userOpHash.
The check requires an EIP-712 typed-data hash.

## The instruction

```text
In ERC-4337 EntryPoint v0.8, how is a UserOperation's userOpHash computed? Answer in one short phrase first, then one sentence.
```

## What it touches

EntryPoint v0.8 hashes UserOperations with EIP-712 and its domain separator.
The domain uses ERC4337, version 1, the chain ID, and the EntryPoint address.
The earlier packed hash with an appended EntryPoint address and chain ID is a different scheme.

## The checks

| Check | What it proves | Area |
| --- | --- | --- |
| `userop_eip712_hash` | Starts with EIP-712 typed-data hashing or its domain-separated 0x1901 formula | account abstraction signatures |

The quiz runs in vanilla, internet, and skills modes.

## Why it matters

A bundler or wallet that uses the older hash scheme produces signatures that EntryPoint v0.8 rejects.
[EntryPoint v0.8's getUserOpHash](https://github.com/eth-infinitism/account-abstraction/blob/v0.8.0/contracts/core/EntryPoint.sol) applies the EIP-712 domain separator.
