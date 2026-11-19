#!/bin/sh
set -eu
cat > /workspace/findings.md <<'REPORT'
# THENA findings

## 1. A direct period update lets anyone erase a week of gauge rewards

Severity: Critical

Location: contracts/VoterV3.sol (_updateFor, vote, poke, updateFor); contracts/MinterUpgradeable.sol (update_period)

update_period is public on the minter. Called directly, it moves active_period to the new week and calls VoterV3.notifyRewardAmount, which raises index by the emissions for the finished week. _updateFor then reads weightsPerEpoch at _epochTimestamp(), the new week, which has no votes yet, so it takes the else branch and sets supplyIndex[gauge] = index without crediting claimable. The attacker calls update_period, then votes 1 wei of weight for every pool (or calls updateFor on every gauge) before anyone calls distribute. Every gauge's claimable for the finished week is lost, and the THE stays in VoterV3. _updateForAfterDistribution reads the previous week and would have been correct.

## 2. GaugeExtraRewarder keeps accruing after its funded period

Severity: High

Location: contracts/GaugeExtraRewarder.sol (updatePool, pendingReward)

updatePool adds (block.timestamp - lastRewardTime) * rewardPerSecond to accRewardPerShare with no cap at lastDistributedTime, then sets lastRewardTime = block.timestamp. After the period ends the rewarder keeps crediting rewards it was never funded for. Early claimers drain tokens owed to other stakers, and when the balance runs out onReward's safeTransfer reverts, which makes GaugeV2 deposit, withdraw and getReward revert for that gauge.

## 3. Killing a gauge leaves its votes in the weekly total

Severity: High

Location: contracts/VoterV3.sol (killGauge, killGaugeTotally, notifyRewardAmount)

killGauge and killGaugeTotally do not remove the gauge's weightsPerEpoch from totWeightsPerEpoch. notifyRewardAmount divides the weekly emissions by the total weight of the finished week, so the killed gauge's share is included in the index but never distributed to any gauge. The share stays stuck in VoterV3, both when a gauge is killed mid-week after receiving votes and when it is killed between update_period and distribute.

## 4. Users can vote for a killed gauge

Severity: High

Location: contracts/VoterV3.sol (_vote)

_vote checks isGauge[_gauge] but not isAlive[_gauge]. killGauge only sets isAlive to false, so a killed gauge still accepts votes. Its votes raise totWeightsPerEpoch and dilute every live gauge, while the killed gauge's own share can never be claimed (_updateFor and _distribute skip dead gauges), so those emissions are locked in VoterV3.

## 5. killGaugeTotally locks its voters out of voting

Severity: High

Location: contracts/VoterV3.sol (killGaugeTotally, _reset, _createGauge)

killGaugeTotally deletes internal_bribes and external_bribes for the gauge, but leaves poolVote and votes of everyone who voted for the pool. It also deletes poolForGauge before reading it, so gauges[pool] is never cleared. When such a voter calls vote, poke or reset, _reset reads gauges[pool] (the dead gauge), then calls IBribe(address(0))._withdraw, which reverts. The voter can never vote or reset that veNFT again, and governance cannot create a replacement gauge because _createGauge requires gauges[pool] == address(0).
REPORT
