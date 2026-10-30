#!/bin/sh
set -eu
cat > /workspace/findings.md <<'MD'
# Kestrel audit findings

## H-01: Collecting protocol fees leaves them in `trackedBalance`, so the next trader or liquidity provider pays for them

**Where:** `KestrelVault.collectProtocolFees`, with `KestrelVault._settle`.

**Cause:** `_settle` credits a swap or deposit with `balanceOf(vault) - trackedBalance[token]`. `trackedBalance` counts pool reserves plus uncollected protocol fees, and every outflow goes through `_send`, which lowers it. `collectProtocolFees` sends the fees out with a direct `safeTransfer` and zeroes `protocolFees[token]`, but never lowers `trackedBalance[token]`. After a collection, the vault's balance sits below `trackedBalance` by the collected amount.

**Impact:** The next `swap` or `addLiquidity` that delivers that token is credited with what it sent minus the collected fees. A trader gets the output for a smaller input, and a liquidity provider gets fewer shares; the shortfall stays in the vault unaccounted. With the default 0.5% slippage, a trade of more than about 200 times the collected amount goes through silently. Smaller swaps and deposits of that token revert on underflow until someone covers the gap, and `skim` reverts too. `collectProtocolFees` is permissionless, so anyone can trigger the loss right before a chosen user's transaction, and it repeats after every collection. This breaks the README's promises that a trader is credited for exactly what they delivered and that the protocol takes only its fee share.

**Severity:** High.

**Fix:** Lower `trackedBalance[token]` by the collected amount, for example by sending the fees with `_send`.

## M-01: Router `addLiquidity` has no minimum on shares minted

**Where:** `KestrelRouter.addLiquidity`.

**Cause:** The router checks the token amounts it pulls, not the shares the vault mints.

**Impact:** A provider has no protection if the vault credits less than the router delivered.

**Severity:** Medium.
MD
