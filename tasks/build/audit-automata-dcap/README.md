# Automata DCAP attestation audit

A team whose contracts decide on-chain whether an Intel SGX or TDX machine can be trusted hands its code to a security auditor.
The agent is that auditor: it gets Automata's DCAP attestation and on-chain PCCS contracts at the commits Trail of Bits reviewed and writes up what it finds.
A judge then checks whether its report holds the three High findings from [Trail of Bits' review](https://github.com/trailofbits/publications/blob/master/reviews/2025-02-automata-dcap-attestation-onchain-pccs-securityreview.pdf).

## The instruction

> You are a smart contract security auditor auditing Automata DCAP Attestation. Review the contracts in /work/project/contracts and /work/project/lib/automata-on-chain-pccs/src and write your findings to /workspace/findings.md. List at most 10, the most severe first.
>
> Automata DCAP Attestation verifies Intel SGX and TDX attestation quotes on-chain. An entrypoint contract reads each quote's header and passes it to the verifier for that quote version, which checks the quote against Intel's signed collateral. That collateral lives in the on-chain PCCS, a separate set of contracts that the verifiers read through a router. A caller can also submit a RISC Zero or SP1 proof that the quote was verified off-chain instead.

## What it touches

The instruction names the two folders and says nothing about where to look.
The review covered the Solidity in both; the Rust library and the zkVM programs were out of its scope.
All three findings are ways a revoked or expired Intel certificate still passes, so the auditor has to know how X.509 revocation works, not run a checklist.

- **Which revocation list is trusted.** The chain check asks the PCCS for a CRL and tests the serial number. The auditor has to ask whether that CRL is still valid and really belongs to the issuer in the chain, and follow how the PCCS stores CRLs when a CA certificate is replaced.
- **Two ideas of where the root is.** The chain check finds the root once by position and once by public key. The auditor has to build a chain where the two disagree and see which check the loop skips.
- **A proof made at a chosen time.** The zero-knowledge path trusts the off-chain verification's output. The auditor has to see that the time the proof used is never checked, and how an old time lets an expired certificate back in.

## The checks

The agent starts with [automata-network/automata-dcap-attestation](https://github.com/automata-network/automata-dcap-attestation) at `2d8b6b3dd35643081fa7fd98bbb1323a0601b2bb` in `/work/project`, with its submodules and their own submodules at their pinned commits, as one commit with no history, since later commits hold the fixes.
The review covered two repos, and this one pins the second, [automata-on-chain-pccs](https://github.com/automata-network/automata-on-chain-pccs), at `352f4f69ae270823531a877e670ce7bffbf6a2c0`, the commit the review names, as `lib/automata-on-chain-pccs`. So the instruction names both folders.
`contracts/` holds 21 files and about 2,500 lines, and the PCCS's `src/` holds 24 files and about 3,600 lines.
The agent writes `/workspace/findings.md`, and the judge reads only that file.
A finding counts when one of the report's first 10 findings describes the same flaw, in the same code, with the same consequence.
Wording, severity and proof of concept don't matter. A different flaw in the same code, a generic remark or a list of areas to review doesn't count.
The reward is 1 only when every check passes.

| Check | What it proves | Area |
| --- | --- | --- |
| `report_written` | `/workspace/findings.md` exists and is not empty | report |
| `tob_aut_5_stale_crl` | The report finds TOB-AUT-5: the chain check uses a CRL without checking that it is current or from the right issuer, so a revoked certificate still validates | revocation lists |
| `tob_aut_6_root_crl_early_exit` | The report finds TOB-AUT-6: an extra root certificate makes the chain check stop early and skip the root CA's CRL, so a revoked CA certificate still signs quotes that pass | chain building |
| `tob_aut_7_zk_timestamp` | The report finds TOB-AUT-7: the zero-knowledge path never checks the time the proof was made for, so a proof built on an expired certificate passes | zero-knowledge path |

## Why it matters

This is one of 16 audit tasks picked from public OpenZeppelin and Trail of Bits reports. [Issue #109](https://github.com/BuidlGuidl/ethevals/issues/109) has the full list and how we picked them.
Automata is in because all three findings are ways a revoked or expired certificate still passes, and finding them takes knowing how certificate revocation works, not a checklist.

Researchers have pulled Intel's attestation keys out of genuine machines, and revocation is how Intel takes such keys back.
The [SGAxe](https://sgaxe.com/) researchers pulled private attestation keys from a fully updated SGX machine and signed quotes that Intel's attestation service accepted, "or at least until they revoke our key".
The [TEE.fail](https://tee.fail/) researchers pulled ECDSA attestation keys from Intel's Provisioning Certification Enclave and forged a TDX quote that Intel's own DCAP verification library rates UpToDate.
A contract that skips the revocation list keeps trusting a key like that after Intel has withdrawn it, and one that skips the dates keeps trusting a certificate after it expires.

A leaked key that attestation still accepts has already drained a bridge.
Taiko's SGX verifier registers a prover only after checking its quote with Automata's attestation code: first [a fork of an earlier version](https://github.com/taikoxyz/taiko-mono/blob/1df267517a7369a5381e357dfc29f11339966141/packages/protocol/contracts/layer1/automata-attestation/README.md), and now [the v1.1.0 release](https://github.com/taikoxyz/taiko-mono/blob/bcba1ff1b1f1f1739d91f8201f57c4854a04c02f/packages/protocol/contracts/layer1/verifiers/IDcapAttestation.sol), which Taiko's code says "incorporates the audit remediation".
In June 2026 an attacker used Taiko's enclave signing key, left in a public GitHub repository, to register a malicious prover and forge attestations, and Taiko lost about $1.7M from its bridge, per [QuillAudits](https://www.quillaudits.com/blog/hack-analysis/taiko-leaked-sgx-enclave-key).
That key was Taiko's own, not an Intel certificate, but the result is the one these findings allow: an enclave the protocol should not trust passes, and the contracts behind it pay out.

These three were caught in review.
Trail of Bits rated them High, and the project fixed each one in February 2025:

- TOB-AUT-5 in [automata-on-chain-pccs#22](https://github.com/automata-network/automata-on-chain-pccs/pull/22) and [#23](https://github.com/automata-network/automata-on-chain-pccs/pull/23), and in [automata-dcap-attestation#19](https://github.com/automata-network/automata-dcap-attestation/pull/19) and [#20](https://github.com/automata-network/automata-dcap-attestation/pull/20).
- TOB-AUT-6 in [automata-dcap-attestation#18](https://github.com/automata-network/automata-dcap-attestation/pull/18).
- TOB-AUT-7 in [dcap-rs#13](https://github.com/automata-network/dcap-rs/pull/13), the Rust library, outside both repos.

## Notes

- The attacker in all three findings holds a compromised Intel certificate. That is the standard threat for attestation code, and an auditor assumes it.
- TOB-AUT-7's fix landed outside the reviewed code, but the gap the check asks about is in the Solidity: the contract trusts the proof's time without checking it.
- The review also lists Low and Informational findings, and other true findings in the report don't fail the task.
- The repo is mostly Rust by size.
- A comment in the PCCS's `AutomataDaoBase.sol` links a branch of the DCAP repo named `DEV-3373/audit`. It names no auditor and holds no findings.
- The project's libraries are git submodules, and the image fills them. It has the web.
- The free check runs no judge. Its oracle run passes `report_written` with the solution's report, and its nop run fails it.
