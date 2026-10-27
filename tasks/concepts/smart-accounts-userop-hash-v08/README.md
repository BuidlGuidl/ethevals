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

A judge reads the question, the right answer, and the final reply, and nothing else.
It passes the reply when it says v0.8 computes an EIP-712 typed-data hash, or gives its `0x1901` formula, in any wording, and fails a reply that gives the old formula as the answer or hedges.

| Check | What it proves | Area |
| --- | --- | --- |
| `answered` | The final reply isn't empty | reply |
| `userop_eip712_hash` | The judge finds an EIP-712 typed-data hash, with the old formula not given as the answer | account abstraction signatures |

The quiz runs in vanilla, internet, and skills modes.

## Why it matters

An account or signer that still uses the old formula signs a hash the v0.8 EntryPoint doesn't check, so every operation fails validation.
The typed-data format also lets a wallet show the user what they sign.
[EntryPoint v0.8's `getUserOpHash`](https://github.com/eth-infinitism/account-abstraction/blob/v0.8.0/contracts/core/EntryPoint.sol#L140-L146) uses the [domain set in its constructor](https://github.com/eth-infinitism/account-abstraction/blob/v0.8.0/contracts/core/EntryPoint.sol#L51-L54).

## Notes

The judge fails a reply that gives the v0.6 and v0.7 formula as v0.8's, even under the EIP-712 name, and a plain hash of the operation or an EIP-191 hash.
It doesn't check every domain field or the operation's encoding.
It's the board's judge, Claude Opus 5.5 at high effort, and it never sees the model's reasoning ([ADR 0016](../../../docs/adr/0016-quizzes-with-explained-answers-use-a-judge.md)).
`tests/hand-cases.json` holds right and wrong replies with their correct marks, and the judge must give each one its mark.
