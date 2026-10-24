# Permit2 signatures after EIP-7702 delegation

This quiz asks how Permit2 checks a signature from an EOA with EIP-7702 delegation.
The fixed answer is ERC-1271, because the delegated account has nonempty code.

## The instruction

```text
An EOA has delegated its code with EIP-7702 to a smart account contract. Its owner signs a Permit2 PermitSingle message with the EOA's private key, and a router submits it to Permit2. Which check does Permit2 use to verify this signature: ecrecover against the EOA's address, or ERC-1271 isValidSignature on the account? Answer ecrecover or ERC-1271 first, then say why in one sentence.
```

## What it touches

- Permit2 signature verification. Permit2 selects its check by the signer's code length, even when an EOA's private key signed the message.
- EIP-7702 delegation. The account stores `0xef0100 || address` as its code, so its code length is nonzero.

## The checks

| Check | What it proves | Area |
| --- | --- | --- |
| `signature_check` | The reply starts with ERC-1271, ERC1271, or EIP-1271, ignoring case and leading whitespace or punctuation | Permit2 signature verification |

The check accepts Markdown around the first token and rejects replies that start with ecrecover.
It checks the selected verification method, without judging the explanation or whether the account accepts the signature.
The quiz runs in vanilla, internet, and skills modes.

## Why it matters

A router can submit a private-key signature that a delegated account rejects through ERC-1271.
Integrations must account for the delegated contract's signature rules.
Permit2's pinned [SignatureVerification.sol](https://github.com/Uniswap/permit2/blob/cc56ad0f3439c502c246fc5cfcc3db92bb8b7219/src/libraries/SignatureVerification.sol#L26-L45) uses ecrecover only for a signer with no code and otherwise calls `isValidSignature`.
[EIP-7702](https://eips.ethereum.org/EIPS/eip-7702#specification) defines the delegation designator that gives the EOA nonempty code.
