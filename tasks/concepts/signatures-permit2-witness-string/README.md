# Permit2 witness type string

The question asks for the exact Permit2 type string for a `VaultDeposit` witness.
The check catches missing type definitions and incorrect ordering.

## The instruction

> You call Permit2's permitWitnessTransferFrom with a witness struct VaultDeposit(address receiver). Write the exact witnessTypeString argument you pass. Give the string first, then one sentence.

## What it touches

Permit2 appends `witnessTypeString` to an existing primary type stub in [PermitHash](https://github.com/Uniswap/permit2/blob/cc56ad0f3439c502c246fc5cfcc3db92bb8b7219/src/libraries/PermitHash.sol).
The argument closes that stub with `VaultDeposit witness)` and adds both referenced type definitions.

[EIP-712](https://eips.ethereum.org/EIPS/eip-712#definition-of-encodetype) sorts those definitions by name, so `TokenPermissions` comes before `VaultDeposit`.
The [interface](https://github.com/Uniswap/permit2/blob/cc56ad0f3439c502c246fc5cfcc3db92bb8b7219/src/interfaces/ISignatureTransfer.sol) requires the `TokenPermissions` definition even though the witness itself has no nested struct.

## The checks

| Check | What it proves | Area |
| --- | --- | --- |
| `witness_type_string` | The first string exactly completes the stub and lists TokenPermissions before VaultDeposit, with optional quotes or backticks | Permit2 and EIP-712 |

The quiz runs in vanilla, internet, and skills modes.
The verifier checks the final reply through RewardKit in a separate container.

## Why it matters

A wrong type string changes the type hash and prevents a valid permit signature from matching.
UniswapX fixed [type ordering](https://github.com/Uniswap/UniswapX/commit/b0cd19ab779a8044d97ecdd1efd7195fcdbcd120) and [nested type hashing](https://github.com/Uniswap/UniswapX/commit/ac1d68e4ab2a9d3014ecd8631162ddbc2355fd39) in separate commits.
