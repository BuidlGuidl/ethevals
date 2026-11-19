#!/bin/sh
set -eu
cat > /workspace/findings.md <<'REPORT'
# ONCHAINID findings

## 1. The validator and the account read different targets from the same batch

Severity: Critical

Location: contracts/modules/validators/ERC734Validator.sol (_scopeAllows, _targetAllowed); contracts/SmartAccount.sol (_execute)

ERC734Validator scopes a batch user operation by decoding its executionCalldata with ERC7579Utils.decodeBatch, and SmartAccount._execute decodes the same bytes again when it runs the batch. decodeBatch checks its offsets against the calldata of the current call, which is validateUserOp (holding a re-encoded copy of the user operation) in the validator and execute in the account. A batch with a crafted, oversized offset therefore resolves to an ordinary external target in the validator and to target zero in the account, with calldata the signer planted. The account turns target zero into itself. A signer with only an ACTION key can make the identity call addKey to give that signer a MANAGEMENT key, or install and uninstall modules.

## 2. Queued approval skips the factory guard

Severity: High

Location: contracts/modules/executors/KeyApprovalModule.sol (_canAutoApprove, approve, _runApproved); contracts/factory/IdentityFactory.sol (revokeAccount)

_canAutoApprove refuses factory calls from keys without MANAGEMENT, but approve() only requires ACTION for any target other than the identity. An ACTION key queues a call to IdentityFactory.revokeAccount through execute, then approves its own request. _runApproved dispatches it with executeFromExecutor under the module's MANAGEMENT key, and the factory revokes the identity's management wallet link for good.

## 3. The key registry is not treated as a privileged target

Severity: High

Location: contracts/modules/executors/KeyApprovalModule.sol (_canAutoApprove); contracts/SmartAccount.sol (_authorizeCall)

ERC734Validator is the key registry and writes keys under the identity that calls it. KeyApprovalModule guards only self-calls and the factory, so a queued call to the registry's addKey auto-approves for an ACTION key. SmartAccount._authorizeCall blocks it only when the validator is also installed as an executor, as the deployment script does, but nothing enforces that. On an identity without that entry, an ACTION key adds itself as a MANAGEMENT key and removes the owner's key.
REPORT
