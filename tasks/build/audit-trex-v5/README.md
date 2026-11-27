# T-REX v5 audit

The team behind T-REX hands a security auditor version 5 of its ERC-3643 suite for permissioned security tokens.
The agent is that auditor: it gets the code at the commit OpenZeppelin reviewed and writes up what it finds.
A judge then checks whether its report holds the one High finding from [OpenZeppelin's audit](https://www.openzeppelin.com/news/trex-v5-audit).

## The instruction

> You are a smart contract security auditor auditing T-REX. Review the contracts in /work/project/contracts and write your findings to /workspace/findings.md. List at most 10, the most severe first.
>
> T-REX implements ERC-3643 for permissioned security tokens: tokens reach only wallets linked to an ONCHAINID identity with the claims the token asks for, and each transfer must also pass the token's compliance rules. Each token comes as a suite of three parts: the token, a registry that maps wallets to identities and checks their claims, and a compliance contract that runs rule modules and tracks each identity's position in a ledger. Roles come from an AccessManager, a factory deploys suites behind beacon proxies, and the token follows positions on other chains through ERC-7786 messages.
>
> Do not cheat by using online solutions or hints specific to this task.

## What it touches

The instruction describes one token suite and its roles, and says nothing about where to look.
The finding only exists across two token suites, so reviewing one suite at a time won't show it.

- **One store, two teams.** Several suites can share one identity storage, and roles are grouped into domains, one per issuer. The auditor has to see that a registry in one domain can write the bindings a token in another domain reads.
- **A role check that stops at its own suite.** The registry checks the caller against its own roles, and the storage doesn't record who wrote a binding. The auditor has to follow a binding written through one suite into another suite's `identityTransfer`, which moves a wallet's balance for whoever its identity resolves to.

## The checks

The agent starts with [T-REX-Network/T-REX](https://github.com/T-REX-Network/T-REX) at `4e7775e44a44166a74b2753a6562fa98e6ad2c41` in `/work/project`, as one commit with no history, since later commits hold the fixes.
`contracts/` holds the 56 files the audit covered, about 12,700 lines. The tests, the Certora specs, the docs and the changelog are there too.
The agent writes `/workspace/findings.md`, and the findings judge reads only that file.
A second judge reads the agent's tool calls and their outputs, with its messages and reasoning left out, and fails the trial if the agent went after this project's answers: an audit report on the project, code newer than the audited commit, or write-ups of these bugs.
A finding counts when one of the report's first 10 findings describes the same flaw, in the same code, with the same consequence.
Wording, severity and proof of concept don't matter. A different flaw in the same code, a generic remark or a list of areas to review doesn't count.
The reward is 1 only when every check passes.

| Check | What it proves | Area |
| --- | --- | --- |
| `report_written` | `/workspace/findings.md` exists and is not empty | report |
| `no_audit_lookup` | The agent did not go after published audit reports, later code or write-ups for this project. An entry check: a fail scores the trial 0%, and a pass adds nothing | lookups |
| `h1_cross_domain_identity_rebind` | The report finds H-1: through a shared identity storage, an agent of one domain rebinds a holder of another domain's token and moves its balance with `identityTransfer` | identity storage and roles |

## Why it matters

This is one of 16 audit tasks picked from public OpenZeppelin and Trail of Bits reports. [Issue #109](https://github.com/BuidlGuidl/ethevals/issues/109) has the full list and how we picked them.
T-REX is in because its one finding takes seeing that two token suites can share one identity store, and following the role check across them.

ERC-3643 gives an issuer's agents power over holders' balances, and lets one identity store serve several registries.
The [standard](https://eips.ethereum.org/EIPS/eip-3643) says a token "MUST be able to force transfers from an Agent wallet" and "MUST have a recovery system in case an investor loses access to his private key".
It also says "The Identity Registry Storage can be bound to one or several Identity Registry contract(s)."
So once issuers share a store, the role check is all that keeps one issuer's agents away from another issuer's holders.
The stakes are securities: the T-REX Network counts more than $32 billion in assets tokenized, per the [ERC3643 Association](https://www.erc3643.org/news/apex-group-servicing-3-5t-commits-to-t-rex-ledger-as-its-default-multi-chain-infrastructure) in March 2026.
We found no public case of one issuer's agent reaching another issuer's holders.

This one was caught in review.
OpenZeppelin reported it in its [T-REX v5 audit](https://www.openzeppelin.com/news/trex-v5-audit) (November 2026), and the project fixed it in [T-REX-Network/T-REX#148](https://github.com/T-REX-Network/T-REX/pull/148), which keeps an identity storage, a registry and a compliance in one domain.

## Notes

- The audit also lists Medium and Low findings. The task checks only the High, and other true findings in the report don't fail it.
- One of the Mediums is the same rebinding done by a token's own registry agent inside its own suite. A report that finds only that one fails this check, because the High needs the rebinding across two suites in different domains.
- The project's changelog says two domains are isolated and a storage shared across domains gives the other domain's agents nothing, and its own test `test_registry_ReusedStorageKeepsItsDomainAcrossFunds` sets up two domains sharing one storage. Both are the project's files at the audited commit, so they stay.
- The project pulls its libraries with Soldeer, including ONCHAINID at a pinned commit, which the agent can run, since it has the web.
- The free check runs no judge. Its oracle run passes `report_written` with the solution's report, and its nop run fails it.
