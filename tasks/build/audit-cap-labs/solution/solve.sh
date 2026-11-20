#!/bin/sh
set -eu
cat > /workspace/findings.md <<'REPORT'
# CAP findings

## 1. Unchecked vault address lets anyone set interest rates

Severity: High

Location: contracts/oracle/libraries/VaultAdapter.sol (rate)

rate(_vault, _asset) has no access control and calls currentUtilizationIndex and utilization on the caller-supplied _vault, then stores the returned index and timestamp in utilizationData[_asset] and updates its utilizationMultiplier in _applySlopes. A contract that returns crafted values can push a real asset's utilization and multiplier as high as the limits allow. The rate oracle reads this for the asset, InterestDebtToken uses it as the interest rate, and every agent borrowing the asset pays inflated interest.

## 2. Burning more than the tracked balance blocks all borrowing of an asset

Severity: High

Location: contracts/vault/libraries/VaultLogic.sol (burn); contracts/vault/Vault.sol (availableBalance); contracts/lendingPool/libraries/ViewLogic.sol (maxBorrowable)

burn subtracts amountOut from totalSupplies and transfers it from the vault's actual balance, but never checks it against totalSupplies - totalBorrows. A user transfers tokens directly to the vault, so the real balance exceeds the tracked available amount, and then burns more than is available. totalSupplies drops below totalBorrows, availableBalance underflows and reverts, and maxBorrowable, which calls it, reverts too, so no agent can borrow that asset.

## 3. Front-run fee auction buyers pay and receive nothing

Severity: High

Location: contracts/feeAuction/FeeAuction.sol (buy, _transferOutAssets)

buy charges currentPrice and sends the buyer the full balance of each listed asset, skipping zero balances. It never reverts when nothing is sent, and the buyer cannot bind the call to an auction round or a minimum amount. An attacker who sees a pending buy front-runs it with the same call, takes all the assets, and doubles the start price for the next round. The victim's transaction then pays the new, higher price and receives nothing.

## 4. Fresh delegations raise health but cannot be slashed

Severity: High

Location: contracts/delegation/Delegation.sol (slashTimestamp, coverage, slashableCollateral); contracts/delegation/providers/symbiotic/NetworkMiddleware.sol (coverage, coverageByVault)

Health and borrowing capacity use coverage, which values every vault's delegation at block.timestamp. Slashing uses slashTimestamp, max((epoch() - 1) * epochDuration, lastBorrow), so only stake delegated before that time can be slashed. Delegators friendly to an agent near liquidation add stake in the current epoch, improving the agent's health, and if it is liquidated their stake is outside the slashable set. They withdraw later unharmed, and when the slashable stake does not cover the debt the protocol absorbs the loss.

## 5. Restaker rewards go to whoever is delegated at repayment time

Severity: High

Location: contracts/delegation/Delegation.sol (distributeRewards); contracts/delegation/providers/symbiotic/NetworkMiddleware.sol (distributeRewards); contracts/lendingPool/libraries/BorrowLogic.sol (repay)

Repayment sends the restaker interest to Delegation.distributeRewards, which splits it among networks and then vaults by their coverage at that block. How long a vault backed the loan is ignored. A vault that sees a large pending repayment delegates to the agent just before it and receives a share of interest accrued over months of risk carried by other vaults.

## 6. StakedCap prices use the decimal count instead of the decimal scale

Severity: High

Location: contracts/oracle/libraries/StakedCapAdapter.sol (price)

price calls convertToAssets(capTokenDecimals) and divides by capTokenDecimals, where capTokenDecimals is 18. It should convert 10**18 shares and divide by 10**18. The resulting staked cUSD price is off by many orders of magnitude, and anyone trading or borrowing against this price extracts the difference.

## 7. Anyone can keep StakedCap yield locked by resetting the vesting timer

Severity: Medium

Location: contracts/token/StakedCap.sol (notify, lockedProfit, totalAssets)

notify is permissionless and, whenever the balance exceeds storedTotal, sets lastNotify to block.timestamp and re-locks the unvested profit plus the new amount. lockedProfit vests linearly from lastNotify over lockDuration and totalAssets subtracts it. Sending 1 wei and calling notify repeatedly restarts vesting every time, so yield already distributed never becomes withdrawable.

## 8. Mint and burn can sandwich oracle price updates

Severity: Medium

Location: contracts/vault/Vault.sol (mint, burn); contracts/vault/Minter.sol (getMintAmount, getBurnAmount)

Mint and burn convert at the current Chainlink prices of the asset and cUSD. When a feed is about to update by more than the mint and burn fees, an attacker mints cUSD at the old price before the update and burns it at the new price after it, keeping the difference, which is taken from the vault's reserves.
REPORT
