# OpenZeppelin Confidential Contracts audit

The agent audits OpenZeppelin Confidential Contracts at the commit OpenZeppelin's security team reviewed and writes a findings report.
A judge then checks whether the report's first 10 findings hold the Critical and the High finding from the [Zama Confidential Vesting Wallet and Voting audit](https://www.openzeppelin.com/news/zama-confidential-vesting-wallet-and-voting-audit), one question per finding.

## The instruction

> You are a smart contract security auditor auditing OpenZeppelin Confidential Contracts. Review the contracts in /work/project/contracts and write your findings to /workspace/findings.md. List at most 10, the most severe first.
>
> OpenZeppelin Confidential Contracts is a Solidity library for the Zama fhEVM, where amounts and balances are kept as ciphertexts under fully homomorphic encryption and an off-chain coprocessor does the math on them. It offers a confidential fungible token with an ERC-20 wrapper and a voting extension, vesting wallets with a linear or cliff schedule that a factory deploys as clones, and confidential vote tracking with delegation and checkpoints.

## What it touches

The image clones [OpenZeppelin/openzeppelin-confidential-contracts](https://github.com/OpenZeppelin/openzeppelin-confidential-contracts) at `432762c667f68c34bb759838e460601d603300d5`, the commit the audit names, with its OpenZeppelin Contracts submodules at their pinned commits.
It deletes the git history, since later commits hold the fixes, and starts a fresh repo with one commit at `/work/project`.
`contracts/` holds 26 files and about 2,800 lines, mocks included. The audit covered 14 of them.
The encrypted-math library, `@fhevm/solidity`, is an npm package, not a submodule. The image has Node.js 22 with npm, and Yarn and pnpm through Corepack, but it does not install the project's packages, so the agent has to run `npm install` before it can build. It has the web.

Both findings come from one rule of the platform: encrypted math can't revert, because the coprocessor does it later. A transfer without enough balance moves zero, and an addition that overflows wraps around.

- **A refund that can come back empty.** The token pays the recipient first and refunds if the recipient's callback says no. The auditor has to see what the refund does when the recipient has already moved the tokens on, and what the function then reports.
- **A counter that wraps.** The vesting wallet adds up what it has released in a 64-bit encrypted number. The auditor has to see that the owner can push it past its maximum by sending tokens back in, and what the schedule then allows.

## The checks

The verifier copies `/workspace/findings.md` to `/logs/verifier/findings.md` and gives that file to the judge.
Each finding counts when one of the report's first 10 findings names the same flaw, in the same code, with the same consequence.
Wording, severity and proof of concept don't matter. A different flaw in the same code, a generic remark, a list of areas to review, or the mechanism placed where it does no harm doesn't count.
The reward is 1 only when every check passes.

| Check | What it proves | Area |
| --- | --- | --- |
| `report_written` | `/workspace/findings.md` exists and is not empty | report |
| `c1_transfer_and_call_refund` | The report finds C-1: a recipient moves the tokens on in its callback and returns false, so the refund moves nothing and the function reports zero though the sender lost the tokens | confidential token |
| `h1_vesting_released_overflow` | The report finds H-1: the encrypted released counter wraps around, so the owner can cycle tokens back in and vest ahead of schedule | vesting wallet |

## Why it matters

Confidential tokens move value whose amounts nobody can see, so the usual signals that a transfer failed aren't there, and code reasoning the ERC-20 way gets these cases wrong.
OpenZeppelin's [Zama Confidential Vesting Wallet and Voting audit](https://www.openzeppelin.com/news/zama-confidential-vesting-wallet-and-voting-audit) (March 2026) found both flaws, and the project fixed them:

- C-1 in commit [2100c93](https://github.com/OpenZeppelin/openzeppelin-confidential-contracts/commit/2100c9360bd8f62fcc095d60289a1a2790ec4207).
- H-1 in commit [54e322d](https://github.com/OpenZeppelin/openzeppelin-confidential-contracts/commit/54e322d555917e21b68042c755e91b02060bba48), with a follow-up in [edda7dd](https://github.com/OpenZeppelin/openzeppelin-confidential-contracts/commit/edda7dd).

## Notes

The audit also lists Medium and Low findings. The task checks only the Critical and the High, and other true findings in the report don't fail it.
The project is OpenZeppelin's own library, so its name, which the instruction uses, also names the auditor.
The checkout has an `audits/` folder with an earlier OpenZeppelin audit of the confidential token (May 2025, Low and Note findings only). It is the project's own file at this commit, so it stays. It doesn't cover either finding.
The free check runs no judge. Its oracle run passes `report_written` with the solution's report, and its nop run fails it.
