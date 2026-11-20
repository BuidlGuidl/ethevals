# Broadcaster provers audit

The agent audits the Crosschain Broadcaster's contracts at the commit OpenZeppelin reviewed and writes a findings report.
A judge then checks whether the report's first 10 findings hold each High finding from [OpenZeppelin's audit](https://www.openzeppelin.com/news/broadcaster-provers-audit), one question per finding.

## The instruction

> You are a smart contract security auditor auditing Crosschain Broadcaster. Review the contracts in /work/project/src/contracts and write your findings to /workspace/findings.md. List at most 10, the most severe first.
>
> Crosschain Broadcaster implements ERC-7888, which lets a contract on one chain prove that a message was published on another chain using storage proofs. A Broadcaster contract records each message in a storage slot, and a Receiver walks a route of chain-specific provers, each proving the next chain's block hash or state root from the one before, then proves the slot itself. Provers come in pairs, one per direction between Ethereum and each of Arbitrum, Optimism, Scroll, Linea, Taiko and ZKsync, and pointer contracts let each prover be upgraded.

## What it touches

The image clones [openintentsframework/broadcaster](https://github.com/openintentsframework/broadcaster) at `e329d3a15d477bb795cf24c82c9da53ec4b693b7`, the commit the audit names, with its five submodules and their own submodules at their pinned commits, including `linea-monorepo` and `scroll-contracts`.
It deletes the git history, since later commits hold the fixes, and starts a fresh repo with one commit at `/work/project`.
`src/contracts/` holds 35 files, about 4,100 lines. The audit covered the twelve provers in `src/contracts/provers` and a diff of the Receiver, the pointer and their interfaces. The tests, docs and scripts are there too.
The project pulls Arbitrum's and Optimism's contract libraries from npm. The image has Node.js 22 with npm, and Yarn and pnpm through Corepack, but it does not install the project's packages, so `forge build` fails until the agent runs `npm install`. It has the web.

Each finding needs a fact that is not in the prover's own code:

- **The deployed contract's storage layout.** The Optimism prover hardcodes a storage slot from the version of Optimism's registry its comment links. Optimism's code is not in the checkout, so the auditor has to check which version is deployed now, on-chain or in Optimism's repo, and where that version keeps the field.
- **How a chain commits to its state.** Linea's state tree is not Ethereum's. The auditor has to notice that one Linea prover uses Linea's own proof format and its partner in the other direction does not.
- **What the caller expects back.** The ZKsync prover's proof checks are sound. The auditor has to follow its return value into the Receiver and see that it hands back the wrong address, which the project's own test also expects.

## The checks

The verifier copies `/workspace/findings.md` to `/logs/verifier/findings.md` and gives that file to the judge.
Each finding counts when one of the report's first 10 findings names the same flaw, in the same code, with the same consequence.
Wording, severity and proof of concept don't matter. A different flaw in the same code, a generic remark, a list of areas to review, or the mechanism placed where it does no harm doesn't count.
The reward is 1 only when every check passes.

| Check | What it proves | Area |
| --- | --- | --- |
| `report_written` | `/workspace/findings.md` exists and is not empty | report |
| `h1_optimism_anchor_game_slot` | The report finds H-1: the Optimism ParentToChildProver reads the anchor game from slot 3, but the deployed registry keeps it in slot 2, so routes that don't end on L1 can't prove OP-chain state | Optimism |
| `h2_linea_child_to_parent_mpt` | The report finds H-2: the Linea ChildToParentProver proves Linea storage with Merkle Patricia proofs and keccak, but Linea uses a Sparse Merkle Tree with MiMC, so routes through the Linea buffer revert | Linea |
| `h3_zksync_returns_publisher` | The report finds H-3: the ZKsync ParentToChildProver returns the message's publisher instead of the broadcaster contract, so the Receiver ties messages to the wrong broadcaster | ZKsync |

## Why it matters

A cross-chain message is only as trustworthy as the weakest prover on its route, and a prover that fails or names the wrong sender breaks every route through that chain.
OpenZeppelin's [Broadcaster provers audit](https://www.openzeppelin.com/news/broadcaster-provers-audit) (March 2026) found these three flaws, and the project fixed them:

- H-1 in [openintentsframework/broadcaster#91](https://github.com/openintentsframework/broadcaster/pull/91).
- H-2 in [openintentsframework/broadcaster#93](https://github.com/openintentsframework/broadcaster/pull/93).
- H-3 in [openintentsframework/broadcaster#83](https://github.com/openintentsframework/broadcaster/pull/83).

## Notes

The audit also lists Medium and Low findings. The task checks only the three Highs, and other true findings in the report don't fail it.
The project's own docs say that Linea uses a Sparse Merkle Tree with MiMC, and its ZKsync test marks the expected account as the publisher. Both are the project's files at the reviewed commit.
Optimism's code is not a submodule, so H-1 needs the agent to look up the deployed registry on the web, as an auditor of this code would.
The free check runs no judge. Its oracle run passes `report_written` with the solution's report, and its nop run fails it.
