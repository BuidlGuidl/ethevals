#!/bin/sh
set -eu
cat > /workspace/findings.md <<'REPORT'
# Intuition findings

## 1. createAtom credits the vault with the protocol fee it pays out

Severity: Medium

Location: src/EthMultiVault.sol (createAtom, _depositOnVaultCreation)

createAtom computes protocolDepositFee on userDeposit and sends it to the protocol vault with the atom creation fee, but passes the whole userDeposit to _depositOnVaultCreation, which adds it to the vault's totalAssets and mints shares for all of it. The vault records assets that already left the contract, so its shares are over-backed on paper and the last redeemer is short. createAtomCompressed, batchCreateAtom, batchCreateAtomCompressed, createTriple and batchCreateTriple repeat the pattern.

## 2. Triple identifiers can collide

Severity: Medium

Location: src/EthMultiVault.sol (tripleHashFromAtoms, createTriple)

The triple hash is keccak256(abi.encodePacked(subject, predicate, object)) over the atoms' variable-length data. Atoms "ab", "c", "d" and "a", "bc", "d" hash the same. An attacker creates atoms whose data concatenate to the same bytes as a triple someone else wants, creates that triple first, and createTriple then refuses the real one as already existing.

## 3. depositTriple computes the atom equity on two different amounts

Severity: Medium

Location: src/EthMultiVault.sol (depositTriple, _depositIntoVault, atomEquityFeeAmount)

_depositIntoVault removes atomEquityFeeAmount(msg.value) from the triple vault's assets, but depositTriple distributes atomEquityFeeAmount(msg.value - protocolFees) to the atoms. The atoms get less than the triple vault left out, and the difference is counted by no vault and stays in the contract.

## 4. Distributing atom equity charges the protocol fee again and strands it

Severity: Medium

Location: src/EthMultiVault.sol (_distributeAtomEquity, _depositIntoVault)

_distributeAtomEquity sends each atom's third through _depositIntoVault, which subtracts a protocol fee from it, although the triple deposit already paid the protocol fee. _distributeAtomEquity discards the returned fee, so it is never paid to the protocol vault and is not in any atom vault's assets. The depositor gets fewer atom shares and the fee is stuck in the contract.

## 5. Vault creation leaves the ghost shares' assets out of the vault

Severity: Medium

Location: src/EthMultiVault.sol (_depositOnVaultCreation, getAtomCost, getTripleCost)

The atom and triple costs include minShare to buy the zero address's ghost shares, and _depositOnVaultCreation mints those shares, but it adds only the receiver's assets to totalAssets. The vault starts with more shares than assets, so shares are worth less than was paid, and the minShare wei is held by the contract but belongs to no vault.
REPORT
