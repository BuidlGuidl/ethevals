# Tidewater DAO

Tidewater DAO governs a treasury of TIDE tokens and ETH. Holders lock TIDE in a vote escrow to get voting power, vote on proposals, and passed proposals run from a timelock after a delay.

## Contracts in scope

| File | What it does |
| --- | --- |
| `src/TideToken.sol` | Fixed-supply ERC-20 governance token. |
| `src/VoteEscrow.sol` | Locks TIDE for up to two years. Voting power is `amount * timeLeft / 104 weeks` and falls to zero at unlock. Keeps a checkpoint history per account for snapshot lookups. Locks can be withdrawn after expiry or exited early for a penalty. |
| `src/TideGovernor.sol` | Proposals, voting, quorum, queueing and execution. Votes count each voter's escrow power at the proposal snapshot. |
| `src/TideTimelock.sol` | Holds the treasury and runs passed proposals after the delay. |

Everything under `src/` is in scope. Tests are not.

## How it works

1. A holder with at least `proposalThreshold` voting power proposes a batch of calls.
2. After `votingDelay` the vote opens and runs for `votingPeriod`. Each account votes once, For, Against or Abstain, with its escrow power at the snapshot.
3. A proposal passes when For beats Against and For plus Abstain reaches `quorumVotes`.
4. Anyone can queue a passed proposal. After the timelock delay (at least one day) anyone can execute it within a 14-day grace period.

Early exit from a lock costs half of the lock's current voting power, paid in TIDE to the treasury. The rest goes back to the holder at once.

Deployment values: 2-day timelock delay, 1-day voting delay, 5-day voting period, 10,000 TIDE threshold, 400,000 TIDE quorum. Total supply is 10,000,000 TIDE.

## Roles and trust

- **Token holders** are untrusted. Any of them may act against the DAO, alone or together.
- **Guardian**: a 4-of-7 security council multisig. Trusted to use its cancel power only against harmful proposals. It cannot propose, vote or move funds.
- **Timelock**: the DAO itself. It changes governor settings, the guardian, and its own delay through proposals.
- There is no owner or admin key anywhere else.

## What the protocol promises

- Voting power comes only from TIDE locked in the escrow, and a snapshot never counts the same TIDE twice.
- Treasury funds move only through a proposal that passed and waited out the timelock delay.
- The guardian can cancel any proposal at any point before it executes, including while it waits in the timelock. A cancelled proposal never executes. This is our defence against a hostile majority.
- Early exit always costs the penalty above; there is no free way out of a lock.

## Known issues

These are accepted and need not be reported:

- `quorumVotes` is a fixed number. As locks decay or grow, governance has to update it with `updateSettings`.
- A proposer whose voting power drops below the threshold after proposing keeps the proposal alive. Only the guardian can cancel it.
- Lock end times round down to whole weeks, so a lock can end up to a week earlier than the time passed to `createLock` or `extendLock`.

## Build and test

Foundry project on Solidity 0.8.30.

```sh
forge build
forge test
```
