# EntryPoint v0.8 UserOperation hash

An account builder asks how EntryPoint v0.8 computes a UserOperation's `userOpHash`.
It is an EIP-712 typed-data hash under the EntryPoint's own domain.
The v0.6 and v0.7 formula still looks right, and it gives a different hash.

## The instruction

> In ERC-4337 EntryPoint v0.8, how is a UserOperation's userOpHash computed? Answer in one sentence.

## What it touches

EntryPoint v0.6 and v0.7 hashed the operation, then hashed that together with the EntryPoint address and the chain id.
Version 0.8 replaces that with an EIP-712 domain.

```text
v0.6 and v0.7:
keccak256(abi.encode(userOp.hash(), entryPoint, chainId))

v0.8:
keccak256(0x1901 || domainSeparator || userOpStructHash)
```

The v0.8 domain has the name "ERC4337", the version "1", the chain id, and the EntryPoint's address.
The "1" is the domain version, not the EntryPoint release.
The live v0.8 EntryPoint at `0x4337084D9E255Ff0702461CF8895CE9E3b5Ff108` reports those fields from `eip712Domain()`.

## The checks

The check reads the start of the reply.
It needs EIP-712 or the domain-separated `0x1901` formula there, and the old formula alone fails.

| Check | What it proves | Area |
| --- | --- | --- |
| `userop_eip712_hash` | Starts with EIP-712 typed-data hashing or its domain-separated 0x1901 formula | account abstraction signatures |

The quiz runs in vanilla, internet, and skills modes.

## Why it matters

An account or signer that still uses the old formula signs a hash the v0.8 EntryPoint doesn't check, so every operation fails validation.
The typed-data format also lets a wallet show the user what they sign.
[EntryPoint v0.8's `getUserOpHash`](https://github.com/eth-infinitism/account-abstraction/blob/v0.8.0/contracts/core/EntryPoint.sol#L140-L146) uses the [domain set in its constructor](https://github.com/eth-infinitism/account-abstraction/blob/v0.8.0/contracts/core/EntryPoint.sol#L51-L54).

## Notes

The check accepts an opening that names EIP-712 with hash or typed-data wording, after lead-ins such as "using" or "it is".
It also accepts an opening `keccak256(0x1901 ...)` formula that names the domain separator.
It refuses the old formula alone, and it does not check every domain field or the operation's encoding.
