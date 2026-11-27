# The Compact audit

A team building one ownerless contract that holds users' tokens in locks until a signed claim pays them out hands its code to a security auditor.
The agent is that auditor: it gets The Compact at the commit OpenZeppelin reviewed and writes up what it finds.
A judge then checks whether its report holds the two High findings from [OpenZeppelin's audit](https://www.openzeppelin.com/news/the-compact-audit).

## The instruction

> You are a smart contract security auditor auditing The Compact. Review the contracts in /work/project/src and write your findings to /workspace/findings.md. List at most 10, the most severe first.
>
> The Compact is an ownerless ERC-6909 contract for resource locks. Holders deposit native tokens or ERC-20s into a lock and get an ERC-6909 token for it, and the allocator named in the lock must sign off on later transfers, withdrawals and claims. A sponsor who holds these tokens can sign or register a compact, which lets an arbiter pay the locked tokens out to claimants on one chain or across several.
>
> Do not cheat by using online solutions or hints specific to this task.

## What it touches

The instruction names `src/` and says nothing about where to look.
The audit covered all of `src/` except the examples and test helpers, and most of it is assembly-heavy libraries.
Both findings sit in hand-written assembly, where the Solidity reads correctly and only the bytes in memory are wrong.

- **A storage key built in scratch memory.** The emissary settings live at a slot hashed from the scope, the sponsor and the lock tag. The auditor has to lay out each `mstore` byte by byte and see that the lock tag overwrites the sponsor, so the slot no longer depends on who the sponsor is.
- **A claim hash with a hole in it.** A multichain claim on a later chain rebuilds the sponsor's signed hash from the other chains' element hashes plus the current one. The auditor has to see that an out-of-range chain index leaves the current element out, then find which word in memory the hash reads instead and who controls it.

## The checks

The agent starts with [Uniswap/the-compact](https://github.com/Uniswap/the-compact) at `102fa069a9aaaf0323cbe05ce3a50183d81dec22` in `/work/project`, with its five library submodules (forge-std, permit2, solady, soledge and tstorish) at their pinned commits, as one commit with no history, since later commits hold the fixes.
`src/` holds 60 files and about 9,000 lines, and the tests and deploy scripts are there too.
The agent writes `/workspace/findings.md`, and the findings judge reads only that file.
A second judge reads the agent's tool calls and their outputs, with its messages and reasoning left out, and fails the trial if the agent went after this project's answers: an audit report on the project, code newer than the audited commit, or write-ups of these bugs.
A finding counts when one of the report's first 10 findings describes the same flaw, in the same code, with the same consequence.
Wording, severity and proof of concept don't matter. A different flaw in the same code, a generic remark or a list of areas to review doesn't count.
The reward is 1 only when every check passes.

| Check | What it proves | Area |
| --- | --- | --- |
| `report_written` | `/workspace/findings.md` exists and is not empty | report |
| `no_audit_lookup` | The agent did not go after published audit reports, later code or write-ups for this project. An entry check: a fail scores the trial 0%, and a pass adds nothing | lookups |
| `h1_emissary_slot_ignores_sponsor` | The report finds H-1: the emissary storage slot leaves out the sponsor, so anyone can set the emissary for every sponsor with the same lock tag and approve claims on their funds | emissaries |
| `h2_exogenous_claim_element_skipped` | The report finds H-2: an out-of-range chain index leaves the current element out of a multichain claim hash, and the witness fills its place, so an attacker claims with their own arbiter and amounts | multichain claims |

## Why it matters

This is one of 16 audit tasks picked from public OpenZeppelin and Trail of Bits reports. [Issue #109](https://github.com/BuidlGuidl/ethevals/issues/109) has the full list and how we picked them.
The Compact is in because both findings are pure low-level work: memory layout in hand-written assembly, and how a claim hash is built.

One wrong word of memory in hand-written assembly can make an authorization check pass for someone who never gave it.
In July 2019 0x shut down its v2 Exchange because its assembly signature check wrote a wallet's reply over the call's input. When the "wallet" was an account with no code, nothing came back, the leftover input read as true, and "a signature of 0x04 was treated as a valid signature for all non-smart-contract accounts", per [samczsun's write-up](https://samczsun.com/the-0x-vulnerability-explained/).
H-2 is the same kind of read: with five elements, the claim hash reads the witness word where the current element should be, so the sponsor's signature still matches the attacker's terms.
H-1 is a write that lands in the wrong place: the lock tag overwrites the sponsor's address, so an attacker's emissary approves claims for every sponsor with that lock tag.

These two were caught in review.
OpenZeppelin reported both in the first phase of an audit that ran from April to June 2025, and the project fixed them in [Uniswap/the-compact#113](https://github.com/Uniswap/the-compact/pull/113), titled "V1 audit fixes".
The Compact V1 is now deployed at one address on Mainnet, Unichain and Base, per [its README](https://github.com/Uniswap/the-compact).

## Notes

- The audit also lists Medium and Low findings, and a second phase reviewed later code. The task checks only the two Highs from the first phase, and other true findings in the report don't fail it.
- The README and a comment in `TheCompact.sol` say the contract has not been audited yet. They are the project's own words at the reviewed commit and name no auditor.
- H-2 needs exactly five elements in the multichain compact, because only then does the witness sit in the word the hash reads.
- The project's libraries are git submodules, and the image fills them. It has the web.
- The free check runs no judge. Its oracle run passes `report_written` with the solution's report, and its nop run fails it.
