# Mainnet P-256 precompile

The user asks whether Ethereum mainnet has a P-256 verification precompile and where it lives.
The check requires yes and address 0x100.

## The instruction

```text
Is there a precompile on Ethereum mainnet today for verifying secp256r1 (P-256, passkey) signatures? If yes, at what address? Answer yes or no first, then the address.
```

## What it touches

EIP-7951 adds P256VERIFY at address 0x100 on Ethereum mainnet through Fusaka.
The address also appears in RIP-7212 deployments on L2s, but the mainnet precompile now exists too.

## The checks

| Check | What it proves | Area |
| --- | --- | --- |
| `p256_precompile_0x100` | Starts with yes and gives 0x100 as the first hexadecimal address | passkey verification |

The quiz runs in vanilla, internet, and skills modes.

## Why it matters

Wallets need the deployed mainnet address to verify passkey signatures through the precompile.
[EIP-7951](https://eips.ethereum.org/EIPS/eip-7951) defines P256VERIFY at 0x100, and [Fusaka's meta EIP](https://eips.ethereum.org/EIPS/eip-7607) records its activation.
