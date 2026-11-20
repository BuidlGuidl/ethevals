# Taraxa bridge audit

Taraxa has almost completely rewritten its bridge between Ethereum and the Taraxa chain, and hands it, with the beacon chain light client it builds on, to a security auditor.
The agent is that auditor: it gets both at the commits Trail of Bits reviewed and writes up what it finds.
A judge then checks whether its report holds two of the High findings from [Trail of Bits' review](https://github.com/trailofbits/publications/blob/master/reviews/2024-07-taraxa-bridge-smart-contracts-v2-securityreview.pdf).

## The instruction

> You are a smart contract security auditor auditing the Taraxa bridge. Review the contracts in /work/project/src and /work/project/lib/beacon-light-client/src and write your findings to /workspace/findings.md. List at most 10, the most severe first.
>
> The Taraxa bridge moves tokens between Ethereum and the Taraxa chain. Each chain runs a light client of the other: on Ethereum, TaraClient follows Taraxa's pillar blocks, and on Taraxa, EthClient builds on the beacon chain light client to follow Ethereum. A bridge contract on each side applies the other side's finalized state changes, and connector contracts lock, release, mint and burn the tokens.

## What it touches

The instruction names both repos and says nothing about where to look.
Both findings are in the bridge, not the beacon chain light client: one in how TaraClient counts validator votes, and one where the bridge applies the other side's state.

- **Counting votes.** The Ethereum-side light client finalizes a pillar block once its signatures carry more than half the validators' weight. The auditor has to check how that weight is added up, and see that nothing stops one signer from counting many times.
- **A payout that calls back.** Applying a bridged state pays recipients before the bridge records that the epoch is done. The auditor has to follow a token transfer into a recipient that can call back, and see what a second pass pays and does to the epoch.

## The checks

The agent starts with [Taraxa-project/bridge](https://github.com/Taraxa-project/bridge) at `f82dd87c7e23358c74f7dc37451ca61110b60942` in `/work/project`, with its submodules at their pinned commits, as one commit with no history, since later commits hold the fixes.
One submodule is the review's second target, [Taraxa-project/beacon-light-client](https://github.com/Taraxa-project/beacon-light-client), pinned at `b2eafadf37e466f7cbed3c5b1ca0a917f152137a`, the commit the review names, so one checkout covers both repos.
`src/` holds the bridge's 29 files and `lib/beacon-light-client/src/` the light client's 23. The review covered the bridge in full and the light client on a best-effort basis.
The agent writes `/workspace/findings.md`, and the judge reads only that file.
A finding counts when one of the report's first 10 findings describes the same flaw, in the same code, with the same consequence.
Wording, severity and proof of concept don't matter. A different flaw in the same code, a generic remark or a list of areas to review doesn't count.
The task gives partial credit: the reward is how many of the two findings the report found, divided by two. `report_written` carries no weight.

| Check | What it proves | Area |
| --- | --- | --- |
| `report_written` | `/workspace/findings.md` exists and is not empty | report |
| `tob_tara_4_duplicate_signatures` | The report finds TOB-TARA-4: `getSignaturesWeight` counts a repeated signature again, so a pillar block without a majority can be finalized | light client |
| `tob_tara_6_apply_state_reentrancy` | The report finds TOB-TARA-6: `applyState` can be re-entered through a token with transfer hooks, so a recipient is paid again and the epoch runs ahead | bridge settlement |

## Why it matters

This is one of 16 audit tasks picked from public OpenZeppelin and Trail of Bits reports. [Issue #109](https://github.com/BuidlGuidl/ethevals/issues/109) has the full list and how we picked them.
The Taraxa bridge is in because its two findings take two kinds of work: checking how validator signatures add up to finality, and following a payout through a token's hook back into the bridge.

A bridge pays out whatever its vote check accepts, so a check that passes without a real majority lets anyone take the funds.
On 6 August 2024 an upgrade to the Ronin bridge "called the initializeV4 function but neglected to call initializeV3". That left `_totalOperatorWeight` at zero and the `minimumVoteWeight` check effectively disabled, by [Rekt's account](https://rekt.news/roninnetwork-rektII).
The bridge lost $12 million, which MEV white hats sent back.
TOB-TARA-4 gets there another way: one signature, repeated, carries a pillar block past the threshold.

Sending a token with hooks hands control to an outside contract, so whatever the code records after it can be raced.
In April 2020 an attacker took nearly $25M from Lendf.Me through imBTC, "a synthetic Bitcoin asset following the ERC777 standard".
Lendf.Me updated its records after the transfer, and its code "did not account for such a transfer or execution to the callback being possible", per [Quantstamp](https://quantstamp.com/blog/how-the-dforce-hacker-used-reentrancy-to-steal-25-million).
Taraxa's bridge records the applied epoch only after its payouts, the same order.

These two were caught in Trail of Bits' review (July 2024), and the project fixed both:

- TOB-TARA-4 in commit [`dd50260`](https://github.com/Taraxa-project/bridge/commit/dd5026078377212ff350a9bf0ed4519d0c880155), which requires the signatures sorted so that none repeats.
- TOB-TARA-6 in commit [`df9e7f3`](https://github.com/Taraxa-project/bridge/commit/df9e7f3303f59b0fb62938980754db890830283d), which moves the epoch increment before the external calls.

## Notes

- The review also lists a third High, TOB-TARA-1, about tokens whose `transfer` doesn't revert on failure. The task leaves it out because it depends on which tokens get bridged, not on an attacker. Other true findings in the report don't fail it.
- TOB-TARA-6 needs a token with transfer hooks, such as an ERC-777 token, to be bridged through the locking connector.
- The review was short, 1.6 engineer-weeks by Trail of Bits' count, and the bridge had just been rewritten, so the report likely leaves out real bugs, and agents may report them.
- The project's libraries, the light client among them, are git submodules and come checked out with the code. The agent has the web.
- The free check runs no judge. Its oracle run passes `report_written` with the solution's report, and its nop run fails it.
