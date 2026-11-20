#!/bin/sh
set -eu
cat > /workspace/findings.md <<'REPORT'
# Crosschain Broadcaster findings

## 1. The Optimism prover reads the anchor game from the wrong storage slot

Severity: High

Location: src/contracts/provers/optimism/ParentToChildProver.sol (ANCHOR_GAME_SLOT, verifyTargetStateCommitment)

verifyTargetStateCommitment takes the anchor game's address from a storage proof of the AnchorStateRegistry at ANCHOR_GAME_SLOT = 3. That is where anchorGame sits in AnchorStateRegistry 2.2.2, the version the comment links. The implementation behind the deployed AnchorStateRegistry proxy is 3.5.0, whose layout keeps anchorGame in slot 2. The storage proof therefore returns a value that is not the anchor game, the account and code checks on it fail, and the prover cannot verify OP-chain state anywhere but L1. Multi-hop routes whose destination is not Ethereum L1 cannot verify any message that passes through Optimism.

## 2. The Linea child-to-parent prover checks Linea state with Ethereum proofs

Severity: High

Location: src/contracts/provers/linea/ChildToParentProver.sol (verifyTargetStateCommitment); src/contracts/libraries/ProverUtils.sol (getSlotFromBlockHeader)

Off Linea, verifyTargetStateCommitment proves the L1 block hash stored in Linea's block hash buffer by calling ProverUtils.getSlotFromBlockHeader on a Linea block header. That helper verifies Merkle Patricia Trie account and storage proofs hashed with keccak256. Linea's state is a Sparse Merkle Tree hashed with MiMC, which the Linea ParentToChildProver handles with SparseMerkleProof. No genuine Linea proof can satisfy the MPT check, so every route that needs to prove the Linea buffer's storage reverts.

## 3. The ZKsync prover returns the publisher instead of the broadcaster

Severity: High

Location: src/contracts/provers/zksync/ParentToChildProver.sol (verifyStorageSlot)

verifyStorageSlot proves the L2 message's inclusion in a settled batch and then returns account = senderAccount, an address from the input that must equal the message's publisher for the slot check to pass. The Receiver uses this return value as the broadcaster's address and folds it into the remote account ID. The correct value is proof.message.sender, the ZkSyncBroadcaster that sent the L2-to-L1 message. Messages proven through this prover are attributed to the publisher rather than the broadcaster, so they do not verify as coming from the real broadcaster. The unit test in test/provers/zksync asserts the publisher as the expected account, so it passes and hides the bug.
REPORT
