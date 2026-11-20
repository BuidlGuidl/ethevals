#!/bin/sh
set -eu
cat > /workspace/findings.md <<'REPORT'
# Automata DCAP Attestation findings

## 1. Certificate chain checks accept expired CRLs and CRLs from the wrong issuer

Severity: High

Location: contracts/bases/X509ChainBase.sol (verifyCertChain); contracts/PCCSRouter.sol (getCrl, _getPcsAttestationData); lib/automata-on-chain-pccs/src/bases/PcsDao.sol (upsertPcsCertificates)

verifyCertChain looks up the CRL for each issuer with pccsRouter.getCrl and tests the certificate's serial number against it. Nothing checks the CRL's validity window or that it was signed by the issuer certificate in the chain: _getPcsAttestationData only checks that the stored bytes are non-empty. In the PCCS, upsertPcsCertificates replaces a CA certificate and leaves the CRL stored for the previous one. An expired CRL, or one issued for an older version of the CA certificate, is therefore used as if it were current. A PCK or CA certificate that Intel revoked after a compromise keeps validating, and its holder can keep signing attestations that the contract accepts.

## 2. An appended root certificate skips the root CA's CRL check

Severity: High

Location: contracts/bases/X509ChainBase.sol (verifyCertChain)

verifyCertChain fetches the root CA's CRL only for the certificate at index n - 2, treating the last entry as the root, but stops the loop as soon as an issuer's public key hash equals ROOTCA_PUBKEY_HASH. If the chain carries an extra copy of the root certificate at the end, the loop breaks at index n - 3, where the intermediate's issuer is already the root, and the intermediate is never checked against the root CRL. Signatures still verify, so a chain through a revoked Platform or Processor CA certificate passes, and quotes signed under it are accepted. The early exit also skips the root's own expiry and self-signature checks.

## 3. Zero-knowledge attestations are not checked for freshness

Severity: High

Location: contracts/verifiers/V3QuoteVerifier.sol (verifyZkOutput); contracts/verifiers/V4QuoteVerifier.sol (verifyZkOutput); contracts/bases/QuoteVerifierBase.sol (checkCollateralHashes)

For RISC Zero and SP1 attestations, verifyZkOutput only compares the collateral hashes in the proof's journal with the PCCS's current collateral. The verification timestamp in the 72 bytes before those hashes is never checked against block.timestamp or the collateral's validity. Once a compromised certificate has expired and dropped off the current CRL, an attacker generates a proof with a timestamp from before its expiry, using today's collateral, and the contract accepts the attestation.
REPORT
