# ONCHAINID audit

The team behind ONCHAINID, the identity layer for T-REX permissioned tokens, has rebuilt each identity as a smart account and hands the code to a security auditor.
The agent is that auditor: it gets ONCHAINID at the commit OpenZeppelin reviewed and writes up what it finds.
A judge then checks whether its report holds the Critical and the two High findings from [OpenZeppelin's audit](https://www.openzeppelin.com/news/onchainid-audit).

## The instruction

> You are a smart contract security auditor auditing ONCHAINID. Review the contracts in /work/project/contracts and write your findings to /workspace/findings.md. List at most 10, the most severe first.
>
> ONCHAINID is the identity layer for T-REX (ERC-3643) permissioned tokens. Identity contracts hold keys and claims, and tokens read them to decide who may hold. This version makes each identity an ERC-7579 smart account that also works with ERC-4337. A validator module keeps the ERC-734 keys and decides what each key may call. A factory deploys identities and links wallets to them. Smaller modules handle queued approvals, recovery, claims and reputation.
>
> Do not cheat by using online solutions or hints specific to this task.

## What it touches

The instruction lists the modules and says nothing about where to look.
All three findings sit on the line between an ACTION key, which may call other contracts, and a MANAGEMENT key, which controls the identity.

- **Two readers of one batch.** The validator checks a batch before it runs, and the account decodes it again to run it. The auditor has to notice that the two decodes measure their bounds against different calldata, and build a batch the two read differently.
- **Two approval paths.** The queued-approval module has an auto-approval path and a queue-then-approve path. The auditor has to compare their guards and see that only one refuses calls to the factory.
- **A target that looks external.** The key registry is a separate contract, so a call to it looks like any outside call. The auditor has to see that it writes keys for the identity that calls it, and trace when the account's own check stops that call and when it doesn't.

## The checks

The agent starts with [T-REX-Network/ONCHAINID](https://github.com/T-REX-Network/ONCHAINID) at `d2096509e3bed2589fff36f6f673498f47e23d73` in `/work/project`, as one commit with no history, since later commits hold the fixes.
`contracts/` holds the 28 files the audit covered, about 4,400 lines. The tests and the deploy script are there too.
The agent writes `/workspace/findings.md`, and the findings judge reads only that file.
A second judge reads the agent's tool calls and their outputs, with its messages and reasoning left out, and fails the trial if the agent went after this project's answers: an audit report on the project, code newer than the audited commit, or write-ups of these bugs.
A finding counts when one of the report's first 10 findings describes the same flaw, in the same code, with the same consequence.
Wording, severity and proof of concept don't matter. A different flaw in the same code, a generic remark or a list of areas to review doesn't count.
The reward is 1 only when every check passes.

| Check | What it proves | Area |
| --- | --- | --- |
| `report_written` | `/workspace/findings.md` exists and is not empty | report |
| `no_audit_lookup` | The agent did not go after published audit reports, later code or write-ups for this project. A gate check: a fail scores the trial 0% | lookups |
| `c1_batch_calldata_targets` | The report finds C-1: the validator and the account read different targets from the same batch calldata, so an ACTION key can make the identity call itself and take MANAGEMENT | batch decoding |
| `h1_queued_factory_call` | The report finds H-1: approving a queued request skips the factory guard that auto-approval has, so an ACTION key can revoke the identity's wallet links | queued approvals |
| `h2_key_registry_target` | The report finds H-2: the queued path treats the key registry as an ordinary target, so where the validator is not also an executor, an ACTION key can add a MANAGEMENT key | key registry |

## Why it matters

This is one of 16 audit tasks picked from public OpenZeppelin and Trail of Bits reports. [Issue #109](https://github.com/BuidlGuidl/ethevals/issues/109) has the full list and how we picked them.
ONCHAINID is in because it has two permission gaps, and one place where the signature checker and the account read the same call differently.

When the code that approves a call and the code that runs it read the calldata differently, an approval for one call can carry another.
In March 2023 [Alchemy reported](https://www.alchemy.com/blog/erc-4337-useroperation-packing-vulnerability) that ERC-4337's EntryPoint and its example VerifyingPaymaster copied calldata into a hash with assembly that trusts the encoded offsets.
So two different user operations could have the same hash, and a paymaster's signature could leave `initCode` and `callData` out, free to change after signing. The EntryPoint was patched, and the post reports no loss.
ONCHAINID's identities work with ERC-4337, and C-1 is the same kind of split, between its validator and its account.

Every path that can change who controls a wallet needs the owner check, and one path without it hands the wallet over.
In July 2017 an attacker drained 153,037 ETH from three Parity multisig wallets, by [OpenZeppelin's account](https://www.openzeppelin.com/news/on-the-parity-wallet-multisig-hack-405a8c12e8f7).
The wallet forwarded unmatched calls to a library, which made the library's public functions "callable by anyone", and its `initWallet` "has no checks to prevent an attacker from calling it after the contract was initialized".
The attacker set the owner list to its own address alone and sent all the funds out.
H-2 is such a path: the key registry writes the identity's keys, and the queued path lets an ACTION key call it.

These three were caught in OpenZeppelin's audit (September 2026), and the project fixed them:

- C-1 in [T-REX-Network/ONCHAINID#39](https://github.com/T-REX-Network/ONCHAINID/pull/39).
- H-1 and H-2 in [T-REX-Network/ONCHAINID#41](https://github.com/T-REX-Network/ONCHAINID/pull/41).

## Notes

- The audit also lists Medium and Low findings. The task checks only the Critical and the two Highs, and other true findings in the report don't fail it.
- The project's own tests in `test/poc/` show escalation paths the developers had already closed, and the auditors had the same files. One of them sends an ACTION key's queued `addKey` to the key registry and passes only because its setup installs the validator as an executor, which is close to H-2.
- The project pulls its libraries with Soldeer, so the agent has to run `forge soldeer install` before it can build. It has the web.
- The free check runs no judge. Its oracle run passes `report_written` with the solution's report, and its nop run fails it.
