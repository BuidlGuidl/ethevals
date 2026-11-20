# Intuition audit

Intuition hands a security auditor the contracts behind its protocol for onchain claims, where every atom and triple has a vault that takes ETH deposits.
The agent is that auditor: it gets the code at the commit Trail of Bits reviewed and writes up what it finds.
A judge then checks whether its report holds the five Medium findings from [Trail of Bits' review](https://github.com/trailofbits/publications/blob/master/reviews/2024-03-intuition-smart-contracts-securityreview.pdf).

## The instruction

> You are a smart contract security auditor auditing Intuition. Review the contracts in /work/project/src and write your findings to /workspace/findings.md. List at most 10, the most severe first.
>
> Intuition is a protocol for making claims onchain. Anyone can create an atom, which stores a piece of data such as a URI, or a triple, which links three atoms as subject, predicate and object, and every atom and triple has its own vault where users deposit ETH for shares. EthMultiVault holds all the vaults and most of the logic behind an upgradeable proxy, and each atom can deploy its own ERC-4337 wallet.

## What it touches

The instruction describes the protocol and says nothing about where to look.
All five findings are in the bookkeeping of `EthMultiVault`, where a deposit pays several fees and buys shares in more than one vault.

- **Fees that leave but stay counted.** The auditor has to follow each fee from where it's computed to where it's sent, and check that every vault's assets drop by what left.
- **One amount computed twice.** A triple deposit buys shares in its three atoms. The auditor has to see that the amount left out of the triple vault and the amount handed to the atoms come from different bases.
- **A fee charged twice and kept.** The atom deposits run through the same helper as a normal deposit, so the auditor has to see that it takes the protocol fee again and that nobody sends it on.
- **Shares without assets.** Each new vault mints ghost shares that the creator pays for. The auditor has to check that those assets reach the vault's books.
- **An identifier that can collide.** A triple's id is a hash of its atoms' packed data, so the auditor has to know that packing variable-length values loses the boundaries between them.

## The checks

The agent starts with [0xIntuition/intuition-tob-audit](https://github.com/0xIntuition/intuition-tob-audit) at `8e80c751600c481164415f7a7f225217cc164ad2` in `/work/project`, with its pinned submodules, as one commit with no history, since later commits hold the fixes.
That is the first of the two commits the review names. The second, `edc4584`, already fixes TOB-INTUITION-6.
`src/` holds 7 files, about 2,000 lines. The review covered `EthMultiVault.sol`, `AtomWallet.sol` and `IntuitionProxy.sol`, and nearly all the logic sits in `EthMultiVault.sol`. The repo ships no tests or scripts at this commit.
The agent writes `/workspace/findings.md`, and the judge reads only that file.
A finding counts when one of the report's first 10 findings describes the same flaw, in the same code, with the same consequence.
Wording, severity and proof of concept don't matter. A different flaw in the same code, a generic remark or a list of areas to review doesn't count.
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

This is one of 16 audit tasks picked from public OpenZeppelin and Trail of Bits reports. [Issue #109](https://github.com/BuidlGuidl/ethevals/issues/109) has the full list and how we picked them.
Intuition is in because three contracts hold five findings: the auditor has to reconcile fees, shares and assets on every deposit path, and spot an identifier that can collide. It's also a little-known project.

Hashing several variable-length values packed together loses the boundaries between them.
Solidity's [ABI docs](https://docs.soliditylang.org/en/latest/abi-spec.html) warn that with `keccak256(abi.encodePacked(a, b))` and both values dynamic, "it is easy to craft collisions", and say `abi.encode` should be preferred.
Foundry's linter rates the same pattern [High](https://www.getfoundry.sh/forge/linting/encode-packed-collision).
That is how a triple's id is built here.

A vault's books decide what every share redeems for, so an amount that is counted but gone, or held but not counted, takes value from depositors or leaves it stranded.
Intuition's live contracts still turn on this bookkeeping: its [bug bounty](https://immunefi.com/bug-bounty/intuition/information/), live since July 2026, pays up to $100,000 and names vault accounting and fee routing among the areas it covers.
We found no public theft from a colliding packed hash, or from a vault that credits a fee it already paid out.

These five were caught in review.
Trail of Bits reported them in its [Intuition smart contracts review](https://github.com/trailofbits/publications/blob/master/reviews/2024-03-intuition-smart-contracts-securityreview.pdf) (March 2024), and the project fixed them:

- TOB-INTUITION-6 in [edc4584](https://github.com/0xIntuition/intuition-tob-audit/commit/edc45845db0246c57b538ed5ab6e1f32becba89c).
- TOB-INTUITION-10 in [0xIntuition/intuition-beta-contracts#33](https://github.com/0xIntuition/intuition-beta-contracts/pull/33).
- TOB-INTUITION-12 and TOB-INTUITION-13 in [028748d](https://github.com/0xIntuition/intuition-tob-audit/commit/028748d1a534367c5eeaa62063695e82f198e049).
- TOB-INTUITION-20 in [0xIntuition/intuition-beta-contracts#36](https://github.com/0xIntuition/intuition-beta-contracts/pull/36).

## Notes

- The review also lists Low and Informational findings. The task checks only the five Mediums, and other true findings in the report don't fail it.
- It's a summary report, so it gives each finding's title and fix but no detail. The questions are written from the code and the fixes.
- TOB-INTUITION-6 and TOB-INTUITION-13 both involve the protocol fee, and TOB-INTUITION-12 and TOB-INTUITION-13 both involve the atom equity of a triple deposit, so each question says which one it is.
- TOB-INTUITION-20 sits next to TOB-INTUITION-7, a Low finding that `createAtom` mints the ghost shares twice. Only the missing assets count for TOB-INTUITION-20.
- The image fills the five pinned submodules in `lib/`: forge-std, solmate, solady, council and openzeppelin-contracts. `.gitmodules` also names openzeppelin-contracts-upgradeable, but the commit pins no copy of it.
- The remappings take OpenZeppelin and the ERC-4337 contracts from npm. The image has Node.js 22 with npm, and Yarn and pnpm through Corepack, but not the project's packages, so `forge build` fails until the agent runs `npm install`. It has the web.
- The free check runs no judge. Its oracle run passes `report_written` with the solution's report, and its nop run fails it.
