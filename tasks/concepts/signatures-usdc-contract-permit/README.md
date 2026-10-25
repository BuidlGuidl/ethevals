# USDC permits from a Safe

A dapp builder asks whether a Safe, which has no private key of its own, can sign a valid USDC permit on mainnet.
Yes. USDC's FiatToken v2.2 accepts ERC-1271 contract signatures for permit.
USDC v2.1 and most EIP-2612 tokens check only an ECDSA signature, which makes "no" the tempting answer.

## The instruction

> Can a Safe smart account, which has no private key of its own, sign a valid USDC permit on Ethereum mainnet? Answer yes or no first, then one sentence.

## What it touches

Mainnet USDC runs FiatToken v2.2, which sends both `permit` overloads through `SignatureChecker`.
When the owner is a contract, `SignatureChecker` calls the owner's ERC-1271 `isValidSignature`.
The Safe approves the signature through its own logic, with its owners' keys, so it never needs a key of its own.

```text
FiatToken v2.1:  permit checks EIP712.recover(...) == owner, so ECDSA only
FiatToken v2.2:  permit calls SignatureChecker, which uses ERC-1271 for contracts
```

## The checks

The check needs a yes at the start of the reply and contract-signature support named somewhere in it.
It refuses no, and it refuses a bare yes.

| Check | What it proves | Area |
| --- | --- | --- |
| `usdc_permit_erc1271` | Starts with yes and names contract signatures, ERC-1271, isValidSignature, SignatureChecker, or v2.2 | contract signatures |

The quiz runs in vanilla, internet, and skills modes.

## Why it matters

A dapp that believes permit is ECDSA-only sends Safe users through a separate `approve` transaction, or turns them away.
USDC already supports the one-signature path for them.
[USDC's permit](https://github.com/circlefin/stablecoin-evm/blob/master/contracts/v2/EIP2612.sol#L102-L109) calls [SignatureChecker](https://github.com/circlefin/stablecoin-evm/blob/master/contracts/util/SignatureChecker.sol#L43-L46), which hands contract owners to ERC-1271.
The [v2.1.0 permit](https://github.com/circlefin/stablecoin-evm/blob/v2.1.0/contracts/v2/EIP2612.sol#L81) only recovered an ECDSA signer.

## Notes

After yes, the check accepts ERC-1271, `isValidSignature`, contract signatures, `SignatureChecker`, or `v2.2`.
It refuses yes without one of those terms, and it does not test a signature against a live Safe.

The Safe needs the standard `CompatibilityFallbackHandler` for ERC-1271.
A Safe without that handler can't sign this way.
