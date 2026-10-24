# USDC permits from a Safe

The user asks whether a Safe without its own private key can authorize a mainnet USDC permit.
The check requires yes and ERC-1271 contract signature support.

## The instruction

```text
Can a Safe smart account, which has no private key of its own, sign a valid USDC permit on Ethereum mainnet? Answer yes or no first, then one sentence.
```

## What it touches

Mainnet USDC's FiatToken v2.2 permit checks signatures through SignatureChecker.
Its bytes-signature overload accepts ERC-1271 contract signatures, including signatures from a Safe with a suitable handler.

## The checks

| Check | What it proves | Area |
| --- | --- | --- |
| `usdc_permit_erc1271` | Starts with yes and identifies ERC-1271 or isValidSignature support | contract signatures |

The quiz runs in vanilla, internet, and skills modes.

## Why it matters

An app that assumes every permit owner needs a private key can block Safe users from its permit flow.
[USDC's EIP2612 implementation](https://github.com/circlefin/stablecoin-evm/blob/master/contracts/v2/EIP2612.sol) uses SignatureChecker for contract owners.
