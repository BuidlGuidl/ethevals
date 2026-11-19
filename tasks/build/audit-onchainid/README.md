# ONCHAINID audit

The agent audits ONCHAINID's contracts at the commit OpenZeppelin reviewed and writes a findings report.
A judge then checks whether the report's first 10 findings hold each Critical and High finding from [OpenZeppelin's audit](https://www.openzeppelin.com/news/onchainid-audit), one question per finding.

## The instruction

> You are a smart contract security auditor auditing ONCHAINID. Review the contracts in /work/project/contracts and write your findings to /workspace/findings.md. List at most 10, the most severe first.
>
> ONCHAINID is the identity layer for T-REX (ERC-3643) permissioned tokens. Identity contracts hold keys and claims, and tokens read them to decide who may hold. This version makes each identity an ERC-7579 smart account that also works with ERC-4337. A validator module keeps the ERC-734 keys and decides what each key may call. A factory deploys identities and links wallets to them. Smaller modules handle queued approvals, recovery, claims and reputation.

## What it touches

The image clones [T-REX-Network/ONCHAINID](https://github.com/T-REX-Network/ONCHAINID) at `d2096509e3bed2589fff36f6f673498f47e23d73`, the commit the audit names.
It deletes the git history, since later commits hold the fixes, and starts a fresh repo with one commit at `/work/project`.
`contracts/` holds the 28 files the audit covered, about 4,400 lines. The tests and the deploy script are there too.
The project pulls its libraries with Soldeer, which the agent can run, since it has the web.

All three findings sit on the line between an ACTION key, which may call other contracts, and a MANAGEMENT key, which controls the identity:

- **Two readers of one batch.** The validator checks a batch before it runs, and the account decodes it again to run it. The auditor has to notice that the two decodes measure their bounds against different calldata, and build a batch the two read differently.
- **Two approval paths.** The queued-approval module has an auto-approval path and a queue-then-approve path. The auditor has to compare their guards and see that only one refuses calls to the factory.
- **A target that looks external.** The key registry is a separate contract, so a call to it looks like any outside call. The auditor has to see that it writes keys for the identity that calls it, and trace when the account's own check stops that call and when it doesn't.

## The checks

The verifier copies `/workspace/findings.md` to `/logs/verifier/findings.md` and gives that file to the judge.
Each finding counts when one of the report's first 10 findings names the same flaw, in the same code, with the same consequence.
Wording, severity and proof of concept don't matter. A different flaw in the same code, a generic remark, a list of areas to review, or the mechanism placed where it does no harm doesn't count.
The reward is 1 only when every check passes.

| Check | What it proves | Area |
| --- | --- | --- |
| `report_written` | `/workspace/findings.md` exists and is not empty | report |
| `c1_batch_calldata_targets` | The report finds C-1: the validator and the account read different targets from the same batch calldata, so an ACTION key can make the identity call itself and take MANAGEMENT | batch decoding |
| `h1_queued_factory_call` | The report finds H-1: approving a queued request skips the factory guard that auto-approval has, so an ACTION key can revoke the identity's wallet links | queued approvals |
| `h2_key_registry_target` | The report finds H-2: the queued path treats the key registry as an ordinary target, so where the validator is not also an executor, an ACTION key can add a MANAGEMENT key | key registry |

## Why it matters

Identity contracts decide who may hold a regulated token, so a key that can raise its own rights can take over the identity.
OpenZeppelin's [ONCHAINID audit](https://www.openzeppelin.com/news/onchainid-audit) (September 2026) found these three flaws, and the project fixed them:

- C-1 in [T-REX-Network/ONCHAINID#39](https://github.com/T-REX-Network/ONCHAINID/pull/39).
- H-1 and H-2 in [T-REX-Network/ONCHAINID#41](https://github.com/T-REX-Network/ONCHAINID/pull/41).

## Notes

The audit also lists Medium and Low findings. The task checks only the Critical and the two Highs, and other true findings in the report don't fail it.
The project's own tests in `test/poc/` show escalation paths the developers had already closed, and the auditors had the same files.
One of them sends an ACTION key's queued `addKey` to the key registry and passes only because its setup installs the validator as an executor, which is close to H-2.
The free check runs no judge. Its oracle run passes `report_written` with the solution's report, and its nop run fails it.
