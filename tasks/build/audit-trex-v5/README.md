# T-REX v5 audit

The agent audits T-REX v5, the ERC-3643 permissioned token suite, at the commit OpenZeppelin reviewed and writes a findings report.
A judge then checks whether the report's first 10 findings hold the High finding from [OpenZeppelin's audit](https://www.openzeppelin.com/news/trex-v5-audit).

## The instruction

> You are a smart contract security auditor auditing T-REX. Review the contracts in /work/project/contracts and write your findings to /workspace/findings.md. List at most 10, the most severe first.
>
> T-REX implements ERC-3643 for permissioned security tokens: tokens reach only wallets linked to an ONCHAINID identity with the claims the token asks for, and each transfer must also pass the token's compliance rules. Each token comes as a suite of three parts: the token, a registry that maps wallets to identities and checks their claims, and a compliance contract that runs rule modules and tracks each identity's position in a ledger. Roles come from an AccessManager, a factory deploys suites behind beacon proxies, and the token follows positions on other chains through ERC-7786 messages.

## What it touches

The image clones [T-REX-Network/T-REX](https://github.com/T-REX-Network/T-REX) at `4e7775e44a44166a74b2753a6562fa98e6ad2c41`, the commit the audit names.
It deletes the git history, since later commits hold the fixes, and starts a fresh repo with one commit at `/work/project`.
`contracts/` holds the 56 files the audit covered, about 12,700 lines. The tests, the Certora specs, the docs and the changelog are there too.
The project pulls its libraries with Soldeer, including ONCHAINID at a pinned commit, which the agent can run, since it has the web.

The finding only exists across two token suites:

- **One store, two teams.** Several suites can share one identity storage, and roles are grouped into domains, one per issuer. The auditor has to see that a registry in one domain can write the bindings a token in another domain reads.
- **A role check that stops at its own suite.** The registry checks the caller against its own roles, and the storage doesn't record who wrote a binding. The auditor has to follow a binding written through one suite into another suite's `identityTransfer`, which moves a wallet's balance for whoever its identity resolves to.

## The checks

The verifier copies `/workspace/findings.md` to `/logs/verifier/findings.md` and gives that file to the judge.
The finding counts when one of the report's first 10 findings names the same flaw, in the same code, with the same consequence.
Wording, severity and proof of concept don't matter. A different flaw in the same code, a generic remark, a list of areas to review, or the mechanism placed where it does no harm doesn't count.
Here that means a report has to place the rebinding across two suites in different domains. The same steps inside one suite, by that token's own agent, are a separate, lower finding.
The reward is 1 only when every check passes.

| Check | What it proves | Area |
| --- | --- | --- |
| `report_written` | `/workspace/findings.md` exists and is not empty | report |
| `h1_cross_domain_identity_rebind` | The report finds H-1: through a shared identity storage, an agent of one domain rebinds a holder of another domain's token and moves its balance with `identityTransfer` | identity storage and roles |

## Why it matters

Permissioned tokens carry securities, and the role split is meant to keep one issuer's operators away from another issuer's holders.
OpenZeppelin's [T-REX v5 audit](https://www.openzeppelin.com/news/trex-v5-audit) (November 2026) found this flaw, and the project fixed it in [T-REX-Network/T-REX#148](https://github.com/T-REX-Network/T-REX/pull/148), which keeps an identity storage, a registry and a compliance in one domain.

## Notes

The audit also lists Medium and Low findings. The task checks only the High, and other true findings in the report don't fail it.
One of the Mediums is the same rebinding done by a token's own registry agent inside its own suite. A report that finds only that one fails this check.
The project's changelog says two domains are isolated and a storage shared across domains gives the other domain's agents nothing, and its own test `test_registry_ReusedStorageKeepsItsDomainAcrossFunds` sets up two domains sharing one storage. Both are the project's files at the audited commit, so they stay.
The free check runs no judge. Its oracle run passes `report_written` with the solution's report, and its nop run fails it.
