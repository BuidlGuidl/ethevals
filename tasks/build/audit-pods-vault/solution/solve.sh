#!/bin/sh
set -eu
cat > /workspace/findings.md <<'REPORT'
# Pods Finance findings

## 1. The deposit queue can grow past what one block can process

Severity: Critical

Location: contracts/libs/DepositQueueLib.sol (remove); contracts/vaults/BaseVault.sol (processQueuedDeposits, refund)

DepositQueueLib.remove copies every remaining entry into a new memory array and writes the whole list back to storage each time it runs. processQueuedDeposits and refund both call it, and refund first scans the queue from the start. An attacker joins the queue with dust deposits from thousands of addresses. After that, processing or refunding even one entry costs more than the block gas limit, so no queued deposit can ever be processed or refunded and all of them are stuck.

## 2. Processed deposits are counted twice when the queue is processed in several calls

Severity: Critical

Location: contracts/vaults/BaseVault.sol (processQueuedDeposits); contracts/vaults/STETHVault.sol (totalAssets)

processQueuedDeposits prices shares against totalAssets() + processedDeposits. totalAssets() is the stETH balance minus the queued total, so deposits processed by an earlier call in the same round are already part of it once they leave the queue. Adding processedDeposits counts them again. Depositors processed in a later call get fewer shares than they should, the result depends on how the queue is split, and they can redeem less than they deposited.

## 3. withdraw rounds the burned shares down, so the vault can be drained

Severity: Critical

Location: contracts/vaults/BaseVault.sol (withdraw, _withdraw)

withdraw converts the requested assets to shares with convertToShares, which rounds down, then burns that many shares and still pays the full asset amount. Asking for less than one share's worth burns zero shares and still pays out. Repeating the call drains the vault once a share is worth more than the gas, and larger withdrawals keep the rounded-off excess.

## 4. A withdrawal can make endRound revert

Severity: High

Location: contracts/vaults/STETHVault.sol (_beforeWithdraw, _afterRoundEnd)

_beforeWithdraw subtracts the withdrawn shares valued at lastSharePrice, rounded down, from lastRoundAssets. That can be less than what left the vault, so lastRoundAssets ends up above totalAssets(). _afterRoundEnd computes totalAssets() - lastRoundAssets, which underflows, so the controller cannot end the round until enough yield accrues.

## 5. BaseVault records a deposit before pulling the tokens

Severity: High

Location: contracts/vaults/BaseVault.sol (_deposit)

BaseVault._deposit pushes the deposit into the queue and only then calls safeTransferFrom. With a token that calls the sender before the transfer, such as ERC-777, the depositor re-enters deposit while the first entry is recorded but unpaid, and the queue credits more than the vault received. STETHVault overrides _deposit with the right order, but any vault that inherits BaseVault's version is exposed.

## 6. Queued deposits are minted shares rounded up

Severity: High

Location: contracts/vaults/BaseVault.sol (_processDeposit)

_processDeposit computes shares with mulDivUp, so a 1-wei deposit gets one whole share. Once a share is worth more than 1 wei, an attacker queues 1-wei deposits from many addresses, receives a share for each when the queue is processed, and redeems them at a profit.
REPORT
