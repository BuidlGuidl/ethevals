#!/bin/sh
set -eu
cat > /workspace/findings.md <<'MD'
# Tidewater DAO audit findings

## H-1: A cancelled proposal still executes through the timelock

**Where:** `TideGovernor.cancel`, `TideTimelock.execute`.

**Cause:** `TideGovernor.cancel` sets `canceled = true` on the proposal but never calls `TideTimelock.cancel` for the operation that `queue` scheduled. `TideTimelock.execute` is open to anyone and only checks the timelock's own `timestamps[id]`, not the governor's proposal state.

**Impact:** The guardian's cancel, the README's defence against a hostile majority, does nothing once a proposal is queued. After the delay anyone calls `TideTimelock.execute` with the proposal's targets, values, calldatas and description hash as salt, and the cancelled proposal runs, for example draining the treasury.

**Severity:** High.

**Fix:** In `cancel`, when the proposal has an `eta`, call `timelock.cancel(timelock.hashOperation(targets, values, calldatas, descriptionHash))`.

## H-2: Early exit leaves voting power in the checkpoint history

**Where:** `VoteEscrow.exitEarly`, read by `VoteEscrow.getPastVotes`, `TideGovernor.propose` and `TideGovernor._castVote`.

**Cause:** `exitEarly` deletes the lock and returns the TIDE but does not call `_writeCheckpoint` with an empty lock. The account's last checkpoint still holds the old amount and end, and `getPastVotes` computes power from it for any later timestamp.

**Impact:** An account that exits keeps its full decaying voting power in every later proposal snapshot while holding no locked TIDE. It can lock the returned TIDE again from another address and vote with both, so a minority outvotes honest lockers and can pass a treasury drain. Repeating with new addresses multiplies the power at the cost of the penalty only.

**Severity:** High.

**Fix:** Write a zero checkpoint in `exitEarly` (and in `withdraw` for consistency) after releasing the lock.
MD
