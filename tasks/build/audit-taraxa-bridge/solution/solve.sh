#!/bin/sh
set -eu
cat > /workspace/findings.md <<'REPORT'
# Taraxa bridge findings

## 1. Repeated signatures finalize pillar blocks without a majority

Severity: High

Location: src/eth/TaraClient.sol (finalizeBlocks, getSignaturesWeight)

finalizeBlocks requires the last block of a batch to collect more than totalWeight / 2 of validator votes, measured by getSignaturesWeight. getSignaturesWeight recovers the signer of every entry in lastBlockSigs and adds validatorVoteCounts[signer] each time, with no check that a signer appears once. A caller who holds one valid signature over the pillar block's vote hash passes it as many times as needed to cross the threshold. A pillar block that only a minority, even one dishonest validator, signed is finalized together with its bridge root, and EthBridge then applies state proven against that root.

## 2. applyState can be re-entered to pay out twice and push the epoch ahead

Severity: High

Location: src/lib/BridgeBase.sol (applyState); src/connectors/ERC20LockingConnectorLogic.sol (applyState)

BridgeBase.applyState is public and has no reentrancy guard. It checks state.epoch == appliedEpoch + 1, calls each connector's applyState, which transfers tokens to the recipients, and only then increments appliedEpoch. If the bridged token calls the recipient on transfer (an ERC-777 or other hook-enabled token), the recipient re-enters applyState with the same proof. The epoch check still passes, so the locking connector pays the recipient again on every nested call until its balance runs out. Each nested call also runs ++appliedEpoch, so the bridge ends several epochs ahead of the other chain and refuses the next valid state, which breaks the bridge until an upgrade.
REPORT
