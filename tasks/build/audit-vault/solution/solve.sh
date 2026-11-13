#!/bin/sh
set -eu
cat > /workspace/findings.md <<'MD'
# Sluice audit findings

## H-1: The first holders out after a market loss leave the whole loss to the rest

**Where:** `SluiceVault.totalAssets`, `SluiceVault._ensureIdle` (withdraw, redeem, claimFees), `SluiceVault._deallocate` (deallocate, reallocate), `BaseStrategy.undeploy`, `BaseStrategy.harvest`.

**Cause:** `totalAssets` values each strategy at `deployedAssets`, the value booked at its last harvest. A withdrawal pays out of the live market and `undeploy` lowers `deployedAssets` by exactly the amount returned. When a market writes off bad debt between harvests, the share price still shows the booked value, and each withdrawal removes booked value one for one with live assets, so the gap between booked and live value stays behind in full.

**Impact:** After a market loss and before the next harvest, holders who redeem are paid at the pre-loss price out of the impaired market. The next harvest books the whole loss against those who stayed. With two 500,000 holders, a 1,000,000 position and a 100,000 write-off, the first to redeem gets 500,000 and the other is left with 400,000 instead of 450,000. A market's bad debt is public on-chain, so holders who watch can always exit first, and `claimFees` pays the treasury out of the impaired market the same way.

**Severity:** High.

**Fix:** Book losses before paying out: harvest a strategy (or compare its live value with `deployedAssets`) before undeploying from it, and charge the withdrawer their share of any unrealised loss.

## H-2: Sold rewards skip the performance fee and the profit unlock

**Where:** `SluiceVault.sellRewards`, `BaseStrategy.claimRewards`, `AaveV3Strategy._claimRewards`, `SluiceVault.totalAssets`, `SluiceVault._harvest`.

**Cause:** Income is charged the performance fee and locked to unlock over `PROFIT_UNLOCK_TIME` only in `_harvest`. `sellRewards` swaps a strategy's rewards and leaves the USDC in the vault's idle balance, which `totalAssets` counts at once.

**Impact:** The treasury earns no fee on reward income, and the income reaches the share price in one step. Anyone who sees an allocator's `sellRewards` transaction can deposit before it and redeem after it, taking a share of rewards the existing holders earned. With 1,000,000 held and 20,000 of rewards sold, a 1,000,000 deposit placed just before the sale leaves with about 10,000 in one block, and the treasury misses 3,000 of fee.

**Severity:** High.

**Fix:** Send the proceeds through harvest: supply them to the strategy before the next harvest, or book them in `sellRewards` as profit, charging the fee and adding the rest to `lockedProfit`.
MD
