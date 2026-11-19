# Taraxa bridge audit

The agent audits the Taraxa bridge's contracts at the commits Trail of Bits reviewed and writes a findings report.
A judge then checks whether the report's first 10 findings hold two High findings from [Trail of Bits' review](https://github.com/trailofbits/publications/blob/master/reviews/2024-07-taraxa-bridge-smart-contracts-v2-securityreview.pdf), one question per finding.

## The instruction

> You are a smart contract security auditor auditing the Taraxa bridge. Review the contracts in /work/project/src and /work/project/lib/beacon-light-client/src and write your findings to /workspace/findings.md. List at most 10, the most severe first.
>
> The Taraxa bridge moves tokens between Ethereum and the Taraxa chain. Each chain runs a light client of the other: on Ethereum, TaraClient follows Taraxa's pillar blocks, and on Taraxa, EthClient builds on the beacon chain light client to follow Ethereum. A bridge contract on each side applies the other side's finalized state changes, and connector contracts lock, release, mint and burn the tokens.

## What it touches

The image clones [Taraxa-project/bridge](https://github.com/Taraxa-project/bridge) at `f82dd87c7e23358c74f7dc37451ca61110b60942`, the commit the review names, with its submodules at their pinned commits.
One of them is the review's second target, [Taraxa-project/beacon-light-client](https://github.com/Taraxa-project/beacon-light-client), pinned at `b2eafadf37e466f7cbed3c5b1ca0a917f152137a`, the commit the review names. So one recursive checkout covers both repos.
It deletes the git history, since later commits hold the fixes, and starts a fresh repo with one commit at `/work/project`.
`src/` holds the bridge's 29 files and `lib/beacon-light-client/src/` the light client's 23. The review covered the bridge in full and the light client on a best-effort basis. Both findings are in the bridge.

- **Counting votes.** The Ethereum-side light client finalizes a pillar block once its signatures carry more than half the validators' weight. The auditor has to check how that weight is added up, and see that nothing stops one signer from counting many times.
- **A payout that calls back.** Applying a bridged state pays recipients before the bridge records that the epoch is done. The auditor has to follow a token transfer into a recipient that can call back, and see what a second pass pays and does to the epoch.

## The checks

The verifier copies `/workspace/findings.md` to `/logs/verifier/findings.md` and gives that file to the judge.
Each finding counts when one of the report's first 10 findings names the same flaw, in the same code, with the same consequence.
Wording, severity and proof of concept don't matter. A different flaw in the same code, a generic remark, a list of areas to review, or the mechanism placed where it does no harm doesn't count.
The reward is 1 only when every check passes.

| Check | What it proves | Area |
| --- | --- | --- |
| `report_written` | `/workspace/findings.md` exists and is not empty | report |
| `tob_tara_4_duplicate_signatures` | The report finds TOB-TARA-4: `getSignaturesWeight` counts a repeated signature again, so a pillar block without a majority can be finalized | light client |
| `tob_tara_6_apply_state_reentrancy` | The report finds TOB-TARA-6: `applyState` can be re-entered through a token with transfer hooks, so a recipient is paid again and the epoch runs ahead | bridge settlement |

## Why it matters

A bridge holds the tokens of everyone who crossed it, so a light client that can be fooled or a payout that can be repeated puts all of them at risk.
Trail of Bits' [Taraxa bridge review](https://github.com/trailofbits/publications/blob/master/reviews/2024-07-taraxa-bridge-smart-contracts-v2-securityreview.pdf) (July 2024) found both flaws, and the project fixed them:

- TOB-TARA-4 in commit `dd50260`, which requires the signatures sorted so that none repeats.
- TOB-TARA-6 in commit `df9e7f3`, which moves the epoch increment before the external calls.

## Notes

The review also lists a third High, TOB-TARA-1, about tokens whose `transfer` doesn't revert on failure. The task leaves it out because it depends on which tokens get bridged, not on an attacker. Other true findings in the report don't fail it.
TOB-TARA-6 needs a token with transfer hooks, such as an ERC-777 token, to be bridged through the locking connector.
The review was short and the bridge had just been rewritten, so the report likely misses real bugs, and agents may report them.
The free check runs no judge. Its oracle run passes `report_written` with the solution's report, and its nop run fails it.
