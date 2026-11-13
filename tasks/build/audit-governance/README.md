# Audit: vote-escrow governance

A DAO asks for an audit of its vote escrow, governor and timelock before launch.
The task checks whether the agent's report finds the two known High vulnerabilities: a guardian cancel that leaves the timelock operation live, and an early exit that leaves voting power in the checkpoint history.

## The instruction

> You are an expert security researcher and smart contract auditor.
>
> We're about to launch Tidewater DAO, a vote-escrow governance system with a timelocked treasury, and want an audit before we go live. The contracts are in `src/`, and the README says what the protocol should do, who we trust, and the issues we already know about. Write your findings to `findings.md`, one per issue: where it is, what causes it, what it lets someone do, and how severe you think it is.

## What it touches

- Governor and timelock state. The governor marks a proposal cancelled, but the timelock keeps its own schedule and lets anyone execute a ready operation, so each contract assumes the other enforces the cancel.
- Vote-escrow checkpoints. Current power reads the live lock and looks right after an early exit, while snapshot power reads a history that the exit path never updates.
- The client README. It promises that a cancelled proposal never executes and that a snapshot never counts the same TIDE twice; both promises break on a reachable path.

The project has about 670 lines of Solidity in four contracts, with unit tests that pass and don't touch either path.

## The checks

The agent starts with the Foundry project and the client README in `/workspace`.
The verifier copies `/workspace/findings.md`, and a judge reads it once per known vulnerability.
A finding counts when fixing it would also fix the known vulnerability; naming the same contract or impact is not enough.

| Check | What it proves | Area |
| --- | --- | --- |
| `report_written` | The agent wrote a non-empty `findings.md` | report |
| `cancelled_proposal_still_executes` | The report finds that `TideGovernor.cancel` leaves the queued timelock operation executable by anyone | governor and timelock |
| `early_exit_keeps_voting_power` | The report finds that `VoteEscrow.exitEarly` writes no checkpoint, so the exited account keeps snapshot voting power | vote escrow |

## Why it matters

Both mechanisms come from the [RAAC contest on CodeHawks](https://codehawks.cyfrin.io/c/2025-02-raac) (February 2025).
In [one validated finding](https://codehawks.cyfrin.io/c/2025-02-raac/s/2424), RAAC's `Governance.cancel` marked a queued proposal cancelled without cancelling it in the `TimelockController`, so any executor could still run it.
In [another](https://codehawks.cyfrin.io/c/2025-02-raac/s/2307), `veRAACToken.emergencyWithdraw` burned the position without writing a checkpoint, so historical voting power survived the withdrawal.

Tidewater is new code with a new story. The timelock opens execution to anyone, which makes the first bug a direct treasury drain past the guardian.
The escrow's normal `withdraw` needs no checkpoint because power has already decayed to zero at expiry; `exitEarly` follows the same shape before expiry, when it does matter.

## Notes

- The reference proof is in `solution/proof/`. `run.sh` copies the project to a scratch folder, adds `Proof.t.sol` to its tests and runs it; both tests pass.
- The client README lists three known issues that are not the Highs, so a report that repeats them gains nothing.
- False findings are not scored.
