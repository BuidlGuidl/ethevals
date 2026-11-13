#!/bin/sh
set -eu
cat > /workspace/findings.md <<'EOF'
# Ballast Staking audit findings

## H-01: harvest() streams BLST owed to queued withdrawals to the remaining stakers

**Where:** `BallastStaking.harvest()`, with `requestWithdrawal()` and `claimWithdrawal()`.

**Cause:** `harvest()` treats `blst.balanceOf(this) - storedAssets - unvestedRewards()` as new rewards. `requestWithdrawal()` moves the queued BLST out of `storedAssets` into `totalQueued`, but the BLST stays in the contract until it is claimed. `harvest()` does not subtract `totalQueued`, so every queued withdrawal is counted as fresh fees.

**Impact:** Anyone can call `harvest()`, and `FeeRouter.distribute()` calls it on every fee run, so this happens in normal operation. The queued BLST is streamed over 7 days to the stakers who stayed, raising their share price. When they withdraw, the contract holds less than `totalQueued`, and the last queued withdrawals revert in `claimWithdrawal()`. With two stakers of 100 BLST, one queues, one harvest later the other can withdraw 200 BLST and the first cannot claim. This breaks promises 1 and 4 in the README.

**Severity:** High. Stakers who queue a withdrawal lose their stake.

**Fix:** Subtract `totalQueued` in `harvest()`: `added = balance - storedAssets - totalQueued - remaining`.

## H-02: Queued withdrawals escape a proposed slash

**Where:** `BallastStaking.requestWithdrawal()`, `slash()`, `claimWithdrawal()`, and `ShortfallModule.proposeSlash()` / `executeSlash()`.

**Cause:** `requestWithdrawal()` fixes the BLST owed at the share price when the request is made, and `slash()` only reduces `storedAssets`, the active stake. `claimWithdrawal()` pays the fixed amount whatever happened in between. Slashes are proposed in public and wait at least a day before they can execute.

**Impact:** A staker who sees a slash proposal queues a withdrawal during the delay and pays none of it. The stakers who stay pay the queued stakers' share, and when the 30% cap binds the market recovers less bad debt. Example: two stakers with 100 BLST each, a 40 BLST slash is proposed, one queues, the slash then takes 30 from the other (the cap on 100 active), who keeps 70 while the leaver gets 100. Pro rata, each would keep 80. The README promises a slash cuts queued withdrawals by the same percentage as active stake. `cancelWithdrawal()` lets the leaver rejoin after the slash at the lower price.

**Severity:** High. Losses move from one set of stakers to another, and shortfall coverage drops.

**Fix:** Keep queued withdrawals exposed until claimed, for example by escrowing shares instead of assets and paying the lower of the value at request and at claim, or by having `slash()` reduce `totalQueued` and each request pro rata through a queue-wide index.
EOF
