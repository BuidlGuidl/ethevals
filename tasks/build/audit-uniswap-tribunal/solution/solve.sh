#!/bin/sh
set -eu
cat > /workspace/findings.md <<'REPORT'
# Tribunal findings

## 1. One wei sent to Tribunal blocks every ERC-20 settleOrRegister deposit

Severity: High

Location: src/Tribunal.sol (settleOrRegister, receive); lib/the-compact/src/lib/DirectDepositLogic.sol (batch deposit check)

settleOrRegister calls batchDeposit or batchDepositAndRegisterFor on The Compact with value: address(this).balance, whatever the commitment's token is. The Compact reverts with InvalidBatchDepositStructure when the first token of a batch is not native and the call carries native value. Tribunal's receive function accepts ETH from anyone, so an attacker sends it 1 wei and every later settleOrRegister that deposits or registers an ERC-20 reverts.

## 2. applySupplementalPriceCurve rejects valid curves and accepts invalid ones

Severity: High

Location: src/lib/PriceCurveLib.sol (applySupplementalPriceCurve, sharesScalingDirection)

applySupplementalPriceCurve ORs sharesScalingDirection(scalingFactor, supplementalScalingFactor) into errorBuffer and reverts when it is non-zero. sharesScalingDirection returns true when both factors scale the same way or one is 1e18, the valid case. So a supplemental curve that agrees with the fill's curve reverts the fill, and one that scales the opposite way passes and is folded into the combined price curve.
REPORT
