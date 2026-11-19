# The Compact audit

The agent audits The Compact's contracts at the commit OpenZeppelin reviewed and writes a findings report.
A judge then checks whether the report's first 10 findings hold each High finding from [OpenZeppelin's audit](https://www.openzeppelin.com/news/the-compact-audit), one question per finding.

## The instruction

> You are a smart contract security auditor auditing The Compact. Review the contracts in /work/project/src and write your findings to /workspace/findings.md. List at most 10, the most severe first.
>
> The Compact is an ownerless ERC-6909 contract for resource locks. Holders deposit native tokens or ERC-20s into a lock and get an ERC-6909 token for it, and the allocator named in the lock must sign off on later transfers, withdrawals and claims. A sponsor who holds these tokens can sign or register a compact, which lets an arbiter pay the locked tokens out to claimants on one chain or across several.

## What it touches

The image clones [Uniswap/the-compact](https://github.com/Uniswap/the-compact) at `102fa069a9aaaf0323cbe05ce3a50183d81dec22`, the commit the audit names, with its five library submodules (forge-std, permit2, solady, soledge and tstorish) at their pinned commits.
It deletes the git history, since later commits hold the fixes, and starts a fresh repo with one commit at `/work/project`.
`src/` holds 60 files, about 9,000 lines, most of them assembly-heavy libraries. The audit covered all of `src/` except the examples and test helpers. The tests and deploy scripts are there too.

Both findings sit in hand-written assembly, where the Solidity reads correctly and only the bytes in memory are wrong:

- **A storage key built in scratch memory.** The emissary settings live at a slot hashed from the scope, the sponsor and the lock tag. The auditor has to lay out each `mstore` byte by byte and see that the lock tag overwrites the sponsor, so the slot no longer depends on who the sponsor is.
- **A claim hash with a hole in it.** A multichain claim on a later chain rebuilds the sponsor's signed hash from the other chains' element hashes plus the current one. The auditor has to see that an out-of-range chain index leaves the current element out, then find which word in memory the hash reads instead and who controls it.

## The checks

The verifier copies `/workspace/findings.md` to `/logs/verifier/findings.md` and gives that file to the judge.
Each finding counts when one of the report's first 10 findings names the same flaw, in the same code, with the same consequence.
Wording, severity and proof of concept don't matter. A different flaw in the same code, a generic remark, a list of areas to review, or the mechanism placed where it does no harm doesn't count.
The reward is 1 only when every check passes.

| Check | What it proves | Area |
| --- | --- | --- |
| `report_written` | `/workspace/findings.md` exists and is not empty | report |
| `h1_emissary_slot_ignores_sponsor` | The report finds H-1: the emissary storage slot leaves out the sponsor, so anyone can set the emissary for every sponsor with the same lock tag and approve claims on their funds | emissaries |
| `h2_exogenous_claim_element_skipped` | The report finds H-2: an out-of-range chain index leaves the current element out of a multichain claim hash, and the witness fills its place, so an attacker claims with their own arbiter and amounts | multichain claims |

## Why it matters

Resource locks hold depositors' tokens until a signed claim releases them, so a slot or hash that stops binding the sponsor lets one user spend another's lock.
OpenZeppelin's [The Compact audit](https://www.openzeppelin.com/news/the-compact-audit) (December 2025) found both flaws, and the project fixed them in [Uniswap/the-compact#113](https://github.com/Uniswap/the-compact/pull/113).

## Notes

The audit also lists Medium and Low findings, and a second phase reviewed later code. The task checks only the two Highs from the first phase, and other true findings in the report don't fail it.
The README and a comment in `TheCompact.sol` say the contract has not been audited yet. They are the project's own words at the reviewed commit and name no auditor.
H-2 needs exactly five elements in the multichain compact, because only then does the witness sit in the word the hash reads.
The free check runs no judge. Its oracle run passes `report_written` with the solution's report, and its nop run fails it.
