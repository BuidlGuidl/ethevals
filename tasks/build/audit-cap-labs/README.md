# CAP audit

The agent audits CAP's contracts at the commit Trail of Bits reviewed and writes a findings report.
A judge then checks whether the report's first 10 findings hold each High and Medium finding from [Trail of Bits' review](https://github.com/trailofbits/publications/blob/master/reviews/2025-05-caplabs-coveredagentprotocol-securityreview.pdf) that an attacker or ordinary user can use, one question per finding.

## The instruction

> You are a smart contract security auditor auditing CAP. Review the contracts in /work/project/contracts and write your findings to /workspace/findings.md. List at most 10, the most severe first.
>
> CAP is a stablecoin protocol. Users deposit stablecoins into a vault to mint cUSD, and can stake cUSD in StakedCap to earn the protocol's yield. Borrowers, called agents, borrow the vault's reserves through the Lender, and restakers back each agent's loans with collateral delegated through Symbiotic. Idle reserves earn yield in outside vaults, and a fee auction sells that yield for cUSD.

## What it touches

The image clones [cap-labs-dev/cap-contracts](https://github.com/cap-labs-dev/cap-contracts) at `56819219e935470271a03d4e3415fcbe810e6b0b`, the commit the review names, with its six submodules (forge-std, LayerZero and others) and their own submodules at their pinned commits.
It deletes the git history, since later commits hold the fixes, and starts a fresh repo with one commit at `/work/project`.
`contracts/` holds 107 files, about 7,900 lines, more than half of them interfaces, storage layouts and deploy helpers. The review covered the vault, StakedCap, the lender and debt tokens, the fee auction, the oracles, delegation and the Symbiotic middleware, and the zap. The LayerZero and EigenLayer integrations and the deploy code were out of scope. The tests are there too.
The project pulls Symbiotic, EigenLayer and OpenZeppelin from npm with Yarn. The image has Node.js 22 with npm, and Yarn and pnpm through Corepack, but it does not install the project's packages, so `forge build` fails until the agent runs `yarn install`. The project asks for Node.js 20, so that install stops until it is told to ignore the version. It has the web.

The eight findings spread over the whole protocol, and several only show once the auditor follows value from one contract into the next:

- **Two ledgers for one balance.** The vault keeps its own totals but pays from its real balance. The auditor has to find the path where the two drift apart and follow the result into the lender's borrow limit.
- **Inputs nobody checks.** The rate adapter trusts whatever vault the caller names, and the price adapter mixes up a decimal count and a decimal scale. The auditor has to read each oracle path and ask who can call it and with what.
- **Time and order.** Vesting restarts on an open call, the fee auction can't tell one buyer's round from the next, mint and burn trade at the price just before an oracle update, and restaker rewards follow whoever is delegated at repayment. The auditor has to think about who moves first and what they gain.
- **Two clocks for one collateral.** Health counts today's delegations, and slashing reaches only older ones. The auditor has to compare the timestamps in the delegation code with Symbiotic's epochs.

## The checks

The verifier copies `/workspace/findings.md` to `/logs/verifier/findings.md` and gives that file to the judge.
Each finding counts when one of the report's first 10 findings names the same flaw, in the same code, with the same consequence.
Wording, severity and proof of concept don't matter. A different flaw in the same code, a generic remark, a list of areas to review, or the mechanism placed where it does no harm doesn't count.
Several findings sit close to others in the review, such as the three front-running findings and the review's lower-severity fee auction and notify findings, so the questions for those findings say which neighbour does not count.
The reward is 1 only when every check passes.

| Check | What it proves | Area |
| --- | --- | --- |
| `report_written` | `/workspace/findings.md` exists and is not empty | report |
| `tob_cap_4_notify_timer_reset` | The report finds TOB-CAP-4: anyone can call `notify()` with 1 wei to restart StakedCap's vesting, so stakers' locked yield keeps being pushed back | staking yield |
| `tob_cap_5_balance_tracking` | The report finds TOB-CAP-5: tokens sent straight to the vault let a burn push tracked supply below borrows, so borrowing the asset stops | vault accounting |
| `tob_cap_12_vault_adapter_rate` | The report finds TOB-CAP-12: anyone can call the rate adapter with a fake vault and inflate a real asset's interest rate | interest rates |
| `tob_cap_13_fee_auction_zero_assets` | The report finds TOB-CAP-13: a front-runner empties the fee auction and the victim's buy still pays, for nothing | fee auction |
| `tob_cap_14_health_vs_slashable` | The report finds TOB-CAP-14: fresh delegations raise an agent's health but can't be slashed, so the protocol takes the loss | delegation |
| `tob_cap_15_reward_delegation_snapshot` | The report finds TOB-CAP-15: restaker interest is split by delegation at repayment, so a vault that delegates just before takes rewards it didn't earn | restaker rewards |
| `tob_cap_17_staked_cap_decimals` | The report finds TOB-CAP-17: the staked cUSD price uses 18 where it needs 1e18, so the price is wrong | oracles |
| `tob_cap_19_oracle_sandwich` | The report finds TOB-CAP-19: minting before and burning after an oracle update takes the price move out of the vault | mint and burn |

## Why it matters

A stablecoin that lends its reserves rests on its accounting, its oracles and the collateral behind each loan, and each of these findings breaks one of them.
Trail of Bits' [Covered Agent Protocol review](https://github.com/trailofbits/publications/blob/master/reviews/2025-05-caplabs-coveredagentprotocol-securityreview.pdf) (May 2025) found all eight. The project fixed seven of them and acknowledged TOB-CAP-15, which it handles in operations only.

## Notes

The review's other Highs and Mediums are not checked, because they rest on an admin's configuration (TOB-CAP-2, -3, -6 and -18) or are design choices (TOB-CAP-16 and -28). Other true findings in the report don't fail the task.
Trail of Bits says it ran short of time on this review and expects more serious bugs in the code, so an agent may report real flaws the review doesn't list. They use up report slots.
The free check runs no judge. Its oracle run passes `report_written` with the solution's report, and its nop run fails it.
