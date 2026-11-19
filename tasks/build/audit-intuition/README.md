# Intuition audit

The agent audits Intuition's vault contracts at the commit Trail of Bits reviewed and writes a findings report.
A judge then checks whether the report's first 10 findings hold each Medium finding from [Trail of Bits' review](https://github.com/trailofbits/publications/blob/master/reviews/2024-03-intuition-smart-contracts-securityreview.pdf), one question per finding.

## The instruction

> You are a smart contract security auditor auditing Intuition. Review the contracts in /work/project/src and write your findings to /workspace/findings.md. List at most 10, the most severe first.
>
> Intuition is a protocol for making claims onchain. Anyone can create an atom, which stores a piece of data such as a URI, or a triple, which links three atoms as subject, predicate and object, and every atom and triple has its own vault where users deposit ETH for shares. EthMultiVault holds all the vaults and most of the logic behind an upgradeable proxy, and each atom can deploy its own ERC-4337 wallet.

## What it touches

The image clones [0xIntuition/intuition-tob-audit](https://github.com/0xIntuition/intuition-tob-audit) at `8e80c751600c481164415f7a7f225217cc164ad2`, the first of the two commits the review names. The second, `edc4584`, already fixes TOB-INTUITION-6.
It deletes the git history, since later commits hold the fixes, and starts a fresh repo with one commit at `/work/project`.
`src/` holds 7 files, about 2,000 lines. The review covered `EthMultiVault.sol`, `AtomWallet.sol` and `IntuitionProxy.sol`, and nearly all the logic sits in `EthMultiVault.sol`.
The repo ships no tests or scripts at this commit.
The image fills the five pinned submodules in `lib/`: forge-std, solmate, solady, council and openzeppelin-contracts. `.gitmodules` also names openzeppelin-contracts-upgradeable, but the commit pins no copy of it. The remappings take OpenZeppelin and the ERC-4337 contracts from npm, and the image has no Node.js, so `forge build` needs the agent to fetch Node and the packages first. It has the web.

All five findings are in the bookkeeping of one contract, where a deposit pays several fees and buys shares in more than one vault:

- **Fees that leave but stay counted.** The auditor has to follow each fee from where it's computed to where it's sent, and check that every vault's assets drop by what left.
- **One amount computed twice.** A triple deposit buys shares in its three atoms. The auditor has to see that the amount left out of the triple vault and the amount handed to the atoms come from different bases.
- **A fee charged twice and kept.** The atom deposits run through the same helper as a normal deposit, so the auditor has to see that it takes the protocol fee again and that nobody sends it on.
- **Shares without assets.** Each new vault mints ghost shares that the creator pays for. The auditor has to check that those assets reach the vault's books.
- **An identifier that can collide.** A triple's id is a hash of its atoms' packed data, so the auditor has to know that packing variable-length values loses the boundaries between them.

## The checks

The verifier copies `/workspace/findings.md` to `/logs/verifier/findings.md` and gives that file to the judge.
Each finding counts when one of the report's first 10 findings names the same flaw, in the same code, with the same consequence.
Wording, severity and proof of concept don't matter. A different flaw in the same code, a generic remark, a list of areas to review, or the mechanism placed where it does no harm doesn't count.
The reward is 1 only when every check passes.

| Check | What it proves | Area |
| --- | --- | --- |
| `report_written` | `/workspace/findings.md` exists and is not empty | report |
| `tob_intuition_6_create_atom_protocol_fee` | The report finds TOB-INTUITION-6: creating an atom pays the protocol fee out but still credits it to the vault | fees |
| `tob_intuition_10_triple_hash_collision` | The report finds TOB-INTUITION-10: triple ids hash packed variable-length atom data, so an attacker can squat on a triple's id | identifiers |
| `tob_intuition_12_atom_equity_base` | The report finds TOB-INTUITION-12: a triple deposit computes the atoms' share on two different amounts, so part of it belongs to no vault | share accounting |
| `tob_intuition_13_atom_equity_protocol_fee` | The report finds TOB-INTUITION-13: distributing a triple deposit to its atoms charges the protocol fee again and leaves it stuck | fees |
| `tob_intuition_20_min_share_assets` | The report finds TOB-INTUITION-20: a new vault mints ghost shares without counting the assets paid for them | share accounting |

## Why it matters

A vault's books decide what every share redeems for, so an amount that is counted but gone, or held but not counted, takes value from depositors or leaves it stranded.
Trail of Bits' [Intuition smart contracts review](https://github.com/trailofbits/publications/blob/master/reviews/2024-03-intuition-smart-contracts-securityreview.pdf) (March 2024) found these five Medium flaws, and the project fixed them:

- TOB-INTUITION-6 in [edc4584](https://github.com/0xIntuition/intuition-tob-audit/commit/edc45845db0246c57b538ed5ab6e1f32becba89c).
- TOB-INTUITION-10 in [0xIntuition/intuition-beta-contracts#33](https://github.com/0xIntuition/intuition-beta-contracts/pull/33).
- TOB-INTUITION-12 and TOB-INTUITION-13 in [028748d](https://github.com/0xIntuition/intuition-tob-audit/commit/028748d1a534367c5eeaa62063695e82f198e049).
- TOB-INTUITION-20 in [0xIntuition/intuition-beta-contracts#36](https://github.com/0xIntuition/intuition-beta-contracts/pull/36).

## Notes

The review also lists Low and Informational findings. The task checks only the five Mediums, and other true findings in the report don't fail it.
It's a summary report, so it gives each finding's title and fix but no detail. The questions are written from the code and the fixes.
TOB-INTUITION-6 and TOB-INTUITION-13 both involve the protocol fee, and TOB-INTUITION-12 and TOB-INTUITION-13 both involve the atom equity of a triple deposit, so each question says which one it is.
TOB-INTUITION-20 sits next to TOB-INTUITION-7, a Low finding that `createAtom` mints the ghost shares twice. Only the missing assets count for TOB-INTUITION-20.
The free check runs no judge. Its oracle run passes `report_written` with the solution's report, and its nop run fails it.
