# Automata DCAP attestation audit

The agent audits Automata's DCAP attestation and on-chain PCCS contracts at the commits Trail of Bits reviewed and writes a findings report.
A judge then checks whether the report's first 10 findings hold each High finding from [Trail of Bits' review](https://github.com/trailofbits/publications/blob/master/reviews/2025-02-automata-dcap-attestation-onchain-pccs-securityreview.pdf), one question per finding.

## The instruction

> You are a smart contract security auditor auditing Automata DCAP Attestation. Review the contracts in /work/project/contracts and /work/project/lib/automata-on-chain-pccs/src and write your findings to /workspace/findings.md. List at most 10, the most severe first.
>
> Automata DCAP Attestation verifies Intel SGX and TDX attestation quotes on-chain. An entrypoint contract reads each quote's header and passes it to the verifier for that quote version, which checks the quote against Intel's signed collateral. That collateral lives in the on-chain PCCS, a separate set of contracts that the verifiers read through a router. A caller can also submit a RISC Zero or SP1 proof that the quote was verified off-chain instead.

## What it touches

The image clones [automata-network/automata-dcap-attestation](https://github.com/automata-network/automata-dcap-attestation) at `2d8b6b3dd35643081fa7fd98bbb1323a0601b2bb`, the commit the review names, with its submodules and their own submodules at their pinned commits.
The review covered two repos, and this one pins the second, [automata-on-chain-pccs](https://github.com/automata-network/automata-on-chain-pccs), at `352f4f69ae270823531a877e670ce7bffbf6a2c0`, the commit the review names, as `lib/automata-on-chain-pccs`. So the instruction names both folders.
It deletes the git history, since later commits hold the fixes, and starts a fresh repo with one commit at `/work/project`.
`contracts/` holds 21 files, about 2,500 lines, and the PCCS's `src/` holds 24 files, about 3,600 lines. The review covered the Solidity in both. The repo is mostly Rust by size; the Rust library and the zkVM programs were out of the review's scope.

All three findings are ways a revoked or expired Intel certificate still passes, so the auditor has to know how X.509 revocation works, not run a checklist:

- **Which revocation list is trusted.** The chain check asks the PCCS for a CRL and tests the serial number. The auditor has to ask whether that CRL is still valid and really belongs to the issuer in the chain, and follow how the PCCS stores CRLs when a CA certificate is replaced.
- **Two ideas of where the root is.** The chain check finds the root once by position and once by public key. The auditor has to build a chain where the two disagree and see which check the loop skips.
- **A proof made at a chosen time.** The zero-knowledge path trusts the off-chain verification's output. The auditor has to see that the time the proof used is never checked, and how an old time lets an expired certificate back in.

## The checks

The verifier copies `/workspace/findings.md` to `/logs/verifier/findings.md` and gives that file to the judge.
Each finding counts when one of the report's first 10 findings names the same flaw, in the same code, with the same consequence.
Wording, severity and proof of concept don't matter. A different flaw in the same code, a generic remark, a list of areas to review, or the mechanism placed where it does no harm doesn't count.
The reward is 1 only when every check passes.

| Check | What it proves | Area |
| --- | --- | --- |
| `report_written` | `/workspace/findings.md` exists and is not empty | report |
| `tob_aut_5_stale_crl` | The report finds TOB-AUT-5: the chain check uses a CRL without checking that it is current or from the right issuer, so a revoked certificate still validates | revocation lists |
| `tob_aut_6_root_crl_early_exit` | The report finds TOB-AUT-6: an extra root certificate makes the chain check stop early and skip the root CA's CRL, so a revoked CA certificate still signs quotes that pass | chain building |
| `tob_aut_7_zk_timestamp` | The report finds TOB-AUT-7: the zero-knowledge path never checks the time the proof was made for, so a proof built on an expired certificate passes | zero-knowledge path |

## Why it matters

Attestation contracts are what lets a chain trust code running in a TEE, so a revoked key that still passes lets whoever stole it speak for the enclave.
Trail of Bits' [Automata DCAP attestation and on-chain PCCS review](https://github.com/trailofbits/publications/blob/master/reviews/2025-02-automata-dcap-attestation-onchain-pccs-securityreview.pdf) (February 2025) rated these three findings High, and the project fixed them:

- TOB-AUT-5 in [automata-on-chain-pccs#22](https://github.com/automata-network/automata-on-chain-pccs/pull/22) and [#23](https://github.com/automata-network/automata-on-chain-pccs/pull/23), and in [automata-dcap-attestation#19](https://github.com/automata-network/automata-dcap-attestation/pull/19) and [#20](https://github.com/automata-network/automata-dcap-attestation/pull/20).
- TOB-AUT-6 in [automata-dcap-attestation#18](https://github.com/automata-network/automata-dcap-attestation/pull/18).
- TOB-AUT-7 in [dcap-rs#13](https://github.com/automata-network/dcap-rs/pull/13), the Rust library, outside both repos.

## Notes

The attacker in all three findings holds a compromised Intel certificate. That is the standard threat for attestation code, and an auditor assumes it.
TOB-AUT-7's fix landed outside the reviewed code, but the gap the check asks about is in the Solidity: the contract trusts the proof's time without checking it.
The review also lists Low and Informational findings, and other true findings in the report don't fail the task.
A comment in the PCCS's `AutomataDaoBase.sol` links a branch of the DCAP repo named `DEV-3373/audit`. It names no auditor and holds no findings.
The free check runs no judge. Its oracle run passes `report_written` with the solution's report, and its nop run fails it.
