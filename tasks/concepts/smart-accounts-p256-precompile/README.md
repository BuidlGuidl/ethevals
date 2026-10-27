# Mainnet P-256 precompile

A passkey wallet builder asks whether Ethereum mainnet has a precompile for verifying P-256 signatures.
Yes. EIP-7951's `P256VERIFY` is at `0x100`, live since the Fusaka upgrade.
Before that upgrade the answer was "only on L2s".

## The instruction

> Is there a precompile on Ethereum mainnet today for verifying secp256r1 (P-256, passkey) signatures? If yes, at what address? Answer yes or no, then give the address.

## What it touches

Passkeys sign with the secp256r1 curve, also called P-256.
RIP-7212 added a verifier for it at `0x100` on several L2s.
EIP-7951 added `P256VERIFY` to Ethereum mainnet at the same address.

| When | P-256 verification on mainnet |
| --- | --- |
| Before Fusaka | no precompile, though some L2s had one at `0x100` |
| Since Fusaka | `P256VERIFY` at `0x100`, 6,900 gas per check |

Fusaka activated on mainnet on 2025-12-03.

## The checks

The check needs a yes at the start of the reply and `0x100` as the first hexadecimal address.
It refuses no, and it refuses a different first address.

| Check | What it proves | Area |
| --- | --- | --- |
| `p256_precompile_0x100` | Starts with yes and gives 0x100 as the first hexadecimal address | passkey verification |

The quiz runs in vanilla, internet, and skills modes.

## Why it matters

A passkey wallet that believes mainnet has no precompile ships a Solidity P-256 verifier and pays for the curve math in EVM code.
The precompile does the same check for a fixed 6,900 gas.
[EIP-7951](https://eips.ethereum.org/EIPS/eip-7951) defines `P256VERIFY` and its gas cost, and [Fusaka's meta EIP](https://eips.ethereum.org/EIPS/eip-7607#activation) records when mainnet got it.

## Notes

The check accepts `0x100` or its zero-padded form after an opening yes.
It refuses a different first hexadecimal value even if `0x100` appears later.
It does not run a signature check or require the upgrade's name.

"Today" in the question means after Fusaka.
Before 2025-12-03 the right answer was no.
