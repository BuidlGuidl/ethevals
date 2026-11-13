# Staking audit

A team asks for an audit of Ballast Staking before launch: BLST holders stake to back a lending protocol, earn its fees as a 7-day reward stream, leave through a 10-day withdrawal queue, and can be slashed to cover bad debt.
The task checks whether the audit report finds the two known Highs, both about how the withdrawal queue meets rewards and slashing.

## The instruction

> You are an expert security researcher and smart contract auditor.
>
> We're about to launch Ballast Staking, where BLST holders stake to back our lending markets and earn their fees, and want an audit before we go live. The contracts are in `src/`, and the README says what the protocol should do, who we trust, and the issues we already know about. Write your findings to `findings.md`, one per issue: where it is, what causes it, what it lets someone do, and how severe you think it is.

## What it touches

The agent starts with a Foundry project in `/workspace`: about 540 lines of in-scope Solidity in `BallastStaking`, `ShortfallModule`, `FeeRouter`, and two small helpers, passing unit tests, and the client's README with roles, promises, scope, and known issues.

- Reward accounting. `harvest()` finds new fees as the balance the contract holds beyond what it already owes. It forgets one thing it owes: BLST waiting in the withdrawal queue, which `requestWithdrawal()` moved out of the active stake but not out of the contract.
- Slashing and the queue. A queued withdrawal is fixed in BLST when it is requested, and a slash takes only from active stake. Slashes are proposed in public and wait a delay, so a staker can step into the queue after the proposal and skip the slash, which the README says must not happen.

Neither bug sits in one line. Each needs the reader to follow one value across two functions, or across two contracts and a delay.

## The checks

A judge reads `/workspace/findings.md` and answers one question per known High: would fixing a finding in the report also fix this vulnerability? A script also checks that the report exists. Every check must pass for a reward of 1. False findings and severity are not scored.

| Check | What it proves | Area |
| --- | --- | --- |
| `harvest_streams_queued_withdrawals` | The report finds that `harvest()` leaves `totalQueued` out of the balance it already owes, so queued withdrawals are streamed to the remaining stakers and the last claims fail | rewards |
| `queued_withdrawal_escapes_slash` | The report finds that a withdrawal fixed in BLST at request time escapes a later slash, so a staker who queues during the public delay pays nothing and the stakers who stay pay more | slashing |
| `report_written` | The agent wrote a non-empty `findings.md` | report |

## Why it matters

The first High carries the mechanism of the Yeet `StakeV2` finding from Immunefi's Yeet audit competition in March 2025, which several auditors reported as critical ([#42382](https://reports.immunefi.com/yeet/42382-sc-critical-calling-stakev2-executerewarddistributionyeet-by-manager-during-an-ongoing-unstaki), [#41456](https://reports.immunefi.com/yeet/41456-sc-critical-executerewarddistributionyeet-will-count-user-withdraws-as-rewards)). There, `accumulatedDeptRewardsYeet()` counted `balanceOf - totalSupply` as rewards while `startUnstake()` had already lowered `totalSupply` for tokens still in the contract. Ballast carries the same gap into a permissionless `harvest()` that the fee router calls on every run, so no privileged caller is needed for it to bite.

The second High carries the mechanism of H-02 in [Code4rena's Kinetiq audit](https://code4rena.com/reports/2025-04-kinetiq) (April 2025): `queueWithdrawal()` stored the amount owed at the exchange rate before a slash, so stakers who queued early were paid in full and the loss fell on those who stayed. Ballast gives the same gap a public slash proposal with a delay, the way safety modules govern slashing, so the window is known in advance.

The proof in `solution/proof/` shows both on this code: run `forge test` there.

## Notes

- The protocol is our own code with its own names and story, not a copy of either contest repo.
- The client README states the promise the second High breaks, as real safety-module docs do. It does not point at the code that breaks it.
- `cancelWithdrawal()` makes the second High worse, since a staker can rejoin at the lower price after the slash. A report may name either path.
- The known issues in the client README (rewards vesting into an empty pool, harvest rounding, governance's slash powers, pause scope) are real but are not checked.
