#!/bin/sh
set -eu
cat > /workspace/findings.md <<'REPORT'
# T-REX findings

## 1. An agent of one domain can take the balances of another domain's token through a shared identity storage

Severity: High

Location: contracts/ERC-3643/base/ERC3643IdentityRegistry.sol (registerIdentity, updateIdentity); contracts/registry/implementation/IdentityRegistryStorage.sol (modifyStoredIdentity); contracts/libraries/AccessManagerSetupLib.sol (commissionSuite); contracts/token/Token.sol (identityTransfer)

Two suites in different domains of one TREXAccessManager can share an IdentityRegistryStorage: a suite can reuse an existing storage, and commissionSuite grants every suite's registry IRS_WRITER on it. The registry checks only that the caller holds the agent role on that registry, and the storage keeps one binding per wallet with no record of which suite wrote it. An AGENT of token B's domain, holding no role in token A, uses B's registry to register a recipient wallet under a token A holder's identity, so the recipient passes A's eligibility check. It then rebinds the holder's wallet to an identity contract it controls and calls identityTransfer on token A from that contract. identityTransfer only checks that the caller is the wallet's resolved identity, needs no allowance, and moves the holder's whole free balance to the recipient. The domains the project calls isolated are not.
REPORT
