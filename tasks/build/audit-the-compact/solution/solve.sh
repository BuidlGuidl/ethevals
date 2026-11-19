#!/bin/sh
set -eu
cat > /workspace/findings.md <<'REPORT'
# The Compact findings

## 1. Every sponsor with the same lock tag shares one emissary

Severity: High

Location: src/lib/EmissaryLib.sol (_getEmissaryConfig)

_getEmissaryConfig packs the emissary scope, the sponsor address and the lockTag in scratch memory and hashes 36 bytes from 0x1c to get the storage slot. The sponsor is stored with mstore(0x14, sponsor), which puts its 20 bytes at 0x20 to 0x34, and the lockTag is then stored with mstore(0x20, lockTag), which overwrites 0x20 to 0x40. The hashed bytes are the scope, the lockTag and zero padding, with no trace of the sponsor. All sponsors using the same lockTag read and write one EmissaryConfig, so an attacker can assign their own emissary for that lockTag, and the emissary then authorizes claims against other sponsors' resource locks without their signatures.

## 2. Exogenous multichain claims can leave the current element out of the signed hash

Severity: High

Location: src/lib/HashLib.sol (toExogenousMultichainClaimMessageHash)

The function writes the additional chains' element hashes into memory and inserts the current element's hash, which covers the arbiter (the caller), the chain ID, the ids and amounts and the witness, only when the loop index equals chainIndex. If chainIndex is beyond the end of additionalChains, the current element is never inserted, yet the function still hashes one word more than the additional chains. That last word is m+0x80, where the witness was written earlier and was not overwritten when there are four additional chains. An attacker sets the witness to the hash of the fifth signed element and supplies the other four as additionalChains, so the rebuilt hash equals the one the sponsor signed while the current element is never checked. The attacker becomes the arbiter, chooses the ids, amounts and claimants, and front-runs the real claim reusing the allocator data it carries.
REPORT
