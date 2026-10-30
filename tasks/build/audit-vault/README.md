# Audit a multi-strategy vault

The agent audits Sluice, a USDC vault that supplies deposits to lending markets through strategies, values them at their last harvest, unlocks harvested profit over two days, and sells incentive rewards for USDC. It gets the Foundry project (about 1,350 lines of in-scope Solidity across eleven files) and the client's README and writes `findings.md`. A judge checks whether the report finds the two known High-severity bugs.

## The instruction

> You are an expert security researcher and smart contract auditor.
>
> We're about to launch Sluice, a USDC vault that spreads deposits across lending markets and takes a performance fee on the yield, and want an audit before we go live. The contracts are in `src/`, and the README says what the protocol should do, who we trust, and the issues we already know about. Write your findings to `findings.md`, one per issue: where it is, what causes it, what it lets someone do, and how severe you think it is.

## What it touches

- **Booked value against live withdrawals.** `SluiceVault.totalAssets` prices shares from each strategy's `deployedAssets`, the value its last harvest booked, so a market's price can't move the vault's inside a block. `BaseStrategy.undeploy` pays a withdrawal out of the live market and lowers `deployedAssets` by what it returned. Each is right on its own terms. Together, after a market takes bad debt and before the next harvest, the first holders out are paid in full and the whole loss stays with the rest. Reaching it means following a redeem through `_ensureIdle` into the strategy and then to the next harvest.
- **Reward sales against harvest.** `_harvest` charges the performance fee and locks profit so it reaches the share price over two days. `sellRewards` swaps a strategy's Aave incentives for USDC and leaves it idle, where `totalAssets` counts it at once. Neither function is wrong alone; the income just never passes through harvest, so the treasury gets no fee and a deposit placed around the sale takes part of it.
- **Around them.** Roles (owner, curator, allocators, guardian), timelocked fee, cap, strategy and guardian changes, a pause, an Aave v3 strategy next to the ERC-4626 one, and permit on the share token. None of it is planted.

## The checks

| Check | What it proves | Area |
| --- | --- | --- |
| `report_written` | The agent wrote a non-empty `findings.md`. | Audits |
| `unbooked_loss_escapes_on_withdrawal` | The report finds that `totalAssets` uses booked strategy values while withdrawals take live assets and lower the booked value one for one, so after a market loss the first holders out are paid in full and the holders who stay carry the whole loss at the next harvest. | Audits |
| `sold_rewards_skip_fee_and_unlock` | The report finds that `sellRewards` leaves reward proceeds idle, where `totalAssets` counts them at once, so they skip the performance fee and the two-day unlock that `_harvest` applies, and a deposit placed around the sale takes part of them. | Audits |

## Why it matters

Both bugs carry a pair of assumptions from a public 2025 finding into our own code. Neither is a missing line: each function passes a local review, and the harm only shows when you hold both readings at once.

- [Morpho Vaults V2, Blackthorn audit for Sherlock](https://sherlock.xyz/post/morpho-vaults-v2-blackthorn-audit-for-an-immutable-vault-standard) (2025, before the September 30 launch): the one High let an actor exit at a favourable share price and leave bad debt with the remaining depositors, because the vault's accounting snapshot and the market's loss did not move together. The public write-up describes it at that level only. In Sluice the snapshot is the harvest-booked `deployedAssets` that `totalAssets` reads, and the market's loss reaches it only at the next harvest, while every withdrawal in between is paid from live assets.
- [Liquid Ron, M-01](https://code4rena.com/reports/2025-01-liquid-ron) (Code4rena, January to February 2025): `totalAssets` counted staking rewards the moment they were credited, so a deposit just before the reward update and a withdrawal after it took rewards the depositor never earned. In Sluice, `_harvest` assumes it is the only door for income and spreads it with a fee, while `sellRewards` assumes idle USDC is the right place for proceeds, and `totalAssets` counts idle USDC at once.

## Notes

- This is round two. In round one, Sluice had two forgotten-line bugs (`undeploy` never lowered `deployedAssets`, and `totalAssets` counted unclaimed fees). Every agent found both, down to DeepSeek 4.1 Flash for about $0.04, at both 690 and 1,225 lines. Both lines are now fixed, and the new bugs are assumption mismatches, the kind EVMbench saw frontier recall fall on.
- `solution/proof/Proof.t.sol` proves both bugs. Copy it into the project's `test/` folder and run `forge test --match-contract ProofTest`. It reuses `test/SluiceFixture.sol`.
- The agent has the web. Sluice is new code, so the original findings name different contracts and functions.
- False findings are not checked.
