# Audit a multi-strategy vault

The agent audits Sluice, a USDC vault that supplies deposits to lending markets through strategies and takes a performance fee on the interest. It gets the Foundry project and the client's README and writes `findings.md`. A judge checks whether the report finds the two known High-severity bugs.

## The instruction

> You are an expert security researcher and smart contract auditor.
>
> We're about to launch Sluice, a USDC vault that spreads deposits across lending markets and takes a performance fee on the yield, and want an audit before we go live. The contracts are in `src/`, and the README says what the protocol should do, who we trust, and the issues we already know about. Write your findings to `findings.md`, one per issue: where it is, what causes it, what it lets someone do, and how severe you think it is.

## What it touches

- **Strategy bookkeeping.** `BaseStrategy` keeps `deployedAssets`, the baseline harvest measures profit against. `deploy` raises it and `undeployAll` zeroes it, but `undeploy` leaves it alone. The bug only shows when you follow a user withdrawal from `SluiceVault._ensureIdle` into the strategy and then on to the next harvest, a different transaction.
- **Fee accounting.** The vault books fees as USDC owed to the treasury and keeps them idle until `claimFees`. `allocate` keeps them aside, but `totalAssets` still counts them, so the share price includes the treasury's money until it is claimed.

## The checks

| Check | What it proves | Area |
| --- | --- | --- |
| `report_written` | The agent wrote a non-empty `findings.md`. | Audits |
| `undeploy_keeps_harvest_baseline` | The report finds that `undeploy` never lowers `deployedAssets`, so the next harvest reads withdrawn assets as a loss and the treasury's fee on real interest is lost. | Audits |
| `accrued_fees_in_total_assets` | The report finds that `totalAssets` counts `accruedFees`, so depositors who redeem before `claimFees` take part of the fee and the ones who stay pay for it. | Audits |

## Why it matters

Both bugs come from public 2025 Code4rena reports. Sluice is our own code with a new story; only the mechanisms carry over.

- [BakerFi Invitational, H-03](https://code4rena.com/reports/2024-12-bakerfi-invitational) (report published February 2025): `StrategySupplyBase.undeploy` did not lower `_deployedAmount`, so `harvest` read a withdrawal as a loss and the performance fee on interest was never collected. In Sluice the same baseline lives in `BaseStrategy.deployedAssets`, and every user withdrawal that reaches a strategy goes through `undeploy`.
- [Liquid Ron, H-01](https://code4rena.com/reports/2025-01-liquid-ron) (contest January to February 2025): `LiquidRon.totalAssets` counted the operator fee still held in the vault, so when the operator withdrew it the share price dropped and depositors lost the difference. In Sluice the treasury's `accruedFees` sit idle in the vault and `totalAssets` counts them until `claimFees`.

## Notes

- `solution/proof/Proof.t.sol` proves both bugs. Copy it into the project's `test/` folder and run `forge test --match-contract ProofTest`.
- The agent has the web. Sluice is new code, so the original findings name different contracts and functions.
- False findings are not checked.
