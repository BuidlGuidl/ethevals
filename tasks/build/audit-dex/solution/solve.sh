#!/bin/sh
set -eu
cat > /workspace/findings.md <<'MD'
# Kestrel audit findings

## H-01: Distributing fees during a live stream counts the stream's remainder twice, so the farm promises more than it holds

**Where:** `KestrelFarm.distributeFees`, with `KestrelFarm._notify`.

**Cause:** `distributeFees` brings every stream of the token up to date and then treats `balanceOf(farm) - unclaimed[token]` as new fees. `unclaimed` only counts rewards stakers have already earned. The part of each live stream that has not streamed yet is still in the farm's balance, so it is counted as new fees. `_notify` then adds the remainder of the target pool's current stream (`rate * (periodFinish - now)`) on top, so that remainder is promised twice.

**Impact:** Every distribution while a stream is running, including the keeper's daily one, grows promised rewards beyond the farm's balance. Stakers who claim first are paid from other stakers' rewards and the last claims revert. A reward someone funded with `fund` for another pool in the same token is counted as fees and streamed to the fee pool's stakers, so that pool's stakers lose it. Anyone can call `distributeFees` to make it worse.

**Severity:** High.

**Fix:** Track every token committed to a stream (funded or distributed and not yet claimed), and treat only the balance above that as new fees.

## M-01: The vault ignores the launch fee while it is 10% or more and charges the 1% tier fee

**Where:** `KestrelVault.swapFee`, with `KestrelLaunchFee.swapFee`.

**Cause:** The launch fee module starts a new launch-tier pool at `startFeeBps` (30% by default, up to 50%) and decays it to 1%. `KestrelVault.swapFee` treats any module answer `>= MAX_FEE_BPS` (10%) as invalid and falls back to the tier fee.

**Impact:** For the early part of every launch, about the first 41 minutes with the defaults, swaps pay 1% instead of the launch fee. Snipers in the first minutes, the users the feature targets, pay 1% instead of about 30%, and liquidity providers lose the launch fee.

**Severity:** Medium.

**Fix:** Give module fees their own upper bound that matches the module's, or clamp instead of falling back.

## M-02: Anyone can create a launch pool early, so the launch fee has decayed before the token launches

**Where:** `KestrelLaunchFee.swapFee`, with `KestrelVault.createPool` and `KestrelRouter.addLiquidity`.

**Cause:** The launch fee decays from the pool's `createdAt`. `createPool` is permissionless for any pair at an enabled tier, and the router only creates a pool that doesn't exist yet.

**Impact:** Anyone can create a token's launch-tier pool as soon as the token is deployed. When the team adds the first liquidity later, the decay period has already run, and the launch charges the 1% tier fee from the first block.

**Severity:** Medium.

**Fix:** Start the launch clock at the pool's first liquidity.
MD
