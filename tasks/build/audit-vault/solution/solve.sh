#!/bin/sh
set -eu
cat > /workspace/findings.md <<'MD'
# Sluice audit findings

## H-1: Withdrawals from a strategy erase the treasury's performance fee

**Where:** `BaseStrategy.undeploy`, used by `SluiceVault._ensureIdle` (withdraw, redeem, claimFees) and `SluiceVault._deallocate` (deallocate, reallocate); read by `BaseStrategy.harvest` and `SluiceVault._harvest`.

**Cause:** `deployedAssets` is the baseline `harvest` measures profit against. `deploy` raises it and `undeployAll` zeroes it, but `undeploy` sends assets to the vault without lowering it. After any partial undeploy the baseline still counts assets that have left the strategy.

**Impact:** The next harvest computes `totalAssets() - deployedAssets` against the stale baseline. Interest earned before the withdrawal reads as a smaller profit or a loss, the baseline resets to the current value, and the fee on that interest is never booked. With 1,000,000 USDC deployed, 50,000 of interest and a 200,000 user withdrawal, harvest books a 150,000 loss and no fee instead of 7,500. Ordinary withdrawals do this with no attacker, and any depositor can time a withdrawal before each harvest to keep the fee from ever being charged. The treasury loses most of its performance-fee revenue.

**Severity:** High.

**Fix:** Lower `deployedAssets` by the amount returned in `undeploy` (floored at zero), or harvest before every undeploy.

## H-2: Unclaimed fees are counted in totalAssets, so depositors take the treasury's fee

**Where:** `SluiceVault.totalAssets`, `SluiceVault._harvest`, `SluiceVault._accrueManagementFee`, `SluiceVault.claimFees`.

**Cause:** `_harvest` books the performance fee (and `_accrueManagementFee` the management fee) as `accruedFees` and leaves the USDC in the vault until `claimFees`. `totalAssets` adds the vault's whole USDC balance and does not subtract `accruedFees`, while `allocate` treats that USDC as reserved.

**Impact:** Between harvest and claim, the share price includes USDC owed to the treasury. With two 500,000 deposits, 100,000 of interest and a 15% fee, a holder who redeems before `claimFees` receives 550,000 instead of 542,500. When `claimFees` pays 15,000, the share price drops and the holder who stayed is left with 535,000. `claimFees` is public, so the drop can be triggered right after a redemption, and new deposits before the claim are overcharged.

**Severity:** High.

**Fix:** Subtract `accruedFees` in `totalAssets`, or take the fee by minting shares to the treasury at harvest.
MD
