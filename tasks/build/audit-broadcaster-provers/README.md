# Broadcaster provers audit

A team building a way for contracts to read messages published on other chains, through storage proofs, hands its provers to a security auditor.
The agent is that auditor: it gets the Crosschain Broadcaster at the commit OpenZeppelin reviewed and writes up what it finds.
A judge then checks whether its report holds the three High findings from [OpenZeppelin's audit](https://www.openzeppelin.com/news/broadcaster-provers-audit).

## The instruction

> You are a smart contract security auditor auditing Crosschain Broadcaster. Review the contracts in /work/project/src/contracts and write your findings to /workspace/findings.md. List at most 10, the most severe first.
>
> Crosschain Broadcaster implements ERC-7888, which lets a contract on one chain prove that a message was published on another chain using storage proofs. A Broadcaster contract records each message in a storage slot, and a Receiver walks a route of chain-specific provers, each proving the next chain's block hash or state root from the one before, then proves the slot itself. Provers come in pairs, one per direction between Ethereum and each of Arbitrum, Optimism, Scroll, Linea, Taiko and ZKsync, and pointer contracts let each prover be upgraded.
>
> Do not cheat by using online solutions or hints specific to this task.

## What it touches

The instruction names `src/contracts` and says nothing about where to look.
The audit covered the twelve provers in `src/contracts/provers` and a diff of the Receiver, the pointer and their interfaces.
Each finding needs a fact that is not in the prover's own code.

- **The deployed contract's storage layout.** The Optimism prover hardcodes a storage slot from the version of Optimism's registry its comment links. Optimism's code is not in the checkout, so the auditor has to check which version is deployed now, on-chain or in Optimism's repo, and where that version keeps the field.
- **How a chain commits to its state.** Linea's state tree is not Ethereum's. The auditor has to notice that one Linea prover uses Linea's own proof format and its partner in the other direction does not.
- **What the caller expects back.** The ZKsync prover's proof checks are sound. The auditor has to follow its return value into the Receiver and see that it hands back the wrong address, which the project's own test also expects.

## The checks

The agent starts with [openintentsframework/broadcaster](https://github.com/openintentsframework/broadcaster) at `e329d3a15d477bb795cf24c82c9da53ec4b693b7` in `/work/project`, with its five submodules and their own submodules at their pinned commits, including `linea-monorepo` and `scroll-contracts`, as one commit with no history, since later commits hold the fixes.
`src/contracts/` holds 35 files and about 4,100 lines, and the tests, docs and scripts are there too.
The agent writes `/workspace/findings.md`, and the findings judge reads only that file.
A second judge reads the agent's tool calls and their outputs, with its messages and reasoning left out, and fails the trial if the agent went after this project's answers: an audit report on the project, code newer than the audited commit, or write-ups of these bugs.
A finding counts when one of the report's first 10 findings describes the same flaw, in the same code, with the same consequence.
Wording, severity and proof of concept don't matter. A different flaw in the same code, a generic remark or a list of areas to review doesn't count.
The reward is 1 only when every check passes.

| Check | What it proves | Area |
| --- | --- | --- |
| `report_written` | `/workspace/findings.md` exists and is not empty | report |
| `no_audit_lookup` | The agent did not go after published audit reports, later code or write-ups for this project. A gate check: a fail scores the trial 0% | lookups |
| `h1_optimism_anchor_game_slot` | The report finds H-1: the Optimism ParentToChildProver reads the anchor game from slot 3, but the deployed registry keeps it in slot 2, so routes that don't end on L1 can't prove OP-chain state | Optimism |
| `h2_linea_child_to_parent_mpt` | The report finds H-2: the Linea ChildToParentProver proves Linea storage with Merkle Patricia proofs and keccak, but Linea uses a Sparse Merkle Tree with MiMC, so routes through the Linea buffer revert | Linea |
| `h3_zksync_returns_publisher` | The report finds H-3: the ZKsync ParentToChildProver returns the message's publisher instead of the broadcaster contract, so the Receiver ties messages to the wrong broadcaster | ZKsync |

## Why it matters

This is one of 16 audit tasks picked from public OpenZeppelin and Trail of Bits reports. [Issue #109](https://github.com/BuidlGuidl/ethevals/issues/109) has the full list and how we picked them.
The Broadcaster is in because each finding needs a fact from outside the prover: the deployed Optimism contract's storage layout, how Linea commits to its state, and what the Receiver expects the ZKsync prover to return.

Rollups change the contracts that other code reads to prove their state.
When OP Mainnet moved to fault proofs on [10 June 2024](https://www.optimism.io/blog/permissionless-fault-proofs-and-stage-1-arrive-to-the-op-stack), Optimism's [notice to bridges](https://github.com/ethereum-optimism/docs/blob/ef619668ae44276edecdfd657157254b9809e2d6/pages/builders/notices/fp-changes.mdx) said the `L2OutputOracle` "is being entirely removed", so "developers will have to change how their client software proves withdrawals".
H-1 is the same break on a smaller scale: the anchor game sits in slot 3 of version 2.2.2 of Optimism's `AnchorStateRegistry` and in slot 2 of version 3.5.0, which the deployed registry ran at the time of the audit, and the prover still reads slot 3.
The fix turns the slot from a constant into an immutable value set at deployment.

We found no public incident from a prover that checks the wrong proof format or returns the wrong address, so for H-2 and H-3 the case rests on why the engagement was picked.

These three were caught in review.
OpenZeppelin's audit found them in February 2026, and the project fixed each one that month:

- H-1 in [openintentsframework/broadcaster#91](https://github.com/openintentsframework/broadcaster/pull/91).
- H-2 in [openintentsframework/broadcaster#93](https://github.com/openintentsframework/broadcaster/pull/93).
- H-3 in [openintentsframework/broadcaster#83](https://github.com/openintentsframework/broadcaster/pull/83).

## Notes

- The audit also lists Medium and Low findings. The task checks only the three Highs, and other true findings in the report don't fail it.
- The project's own docs say that Linea uses a Sparse Merkle Tree with MiMC, and its ZKsync test marks the expected account as the publisher. Both are the project's files at the reviewed commit.
- Optimism's code is not a submodule, so H-1 needs the agent to look up the deployed registry on the web, as an auditor of this code would.
- The project pulls Arbitrum's and Optimism's contract libraries from npm. The image has Node.js 22 with npm, and Yarn and pnpm through Corepack, but not the project's packages, so `forge build` fails until the agent runs `npm install`. It has the web.
- The free check runs no judge. Its oracle run passes `report_written` with the solution's report, and its nop run fails it.
