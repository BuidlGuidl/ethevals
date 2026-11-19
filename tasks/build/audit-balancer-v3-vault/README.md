# Balancer V3 Vault audit

The agent audits the Balancer V3 Vault at the commit Trail of Bits reviewed and writes a findings report.
A judge then checks whether the report's first 10 findings hold each of the three High findings from the Vault round of [Trail of Bits' review](https://github.com/trailofbits/publications/blob/master/reviews/2024-12-balancer-v3-securityreview.pdf), one question per finding.

## The instruction

> You are a smart contract security auditor auditing Balancer V3. Review the contracts in /work/project/pkg/vault and write your findings to /workspace/findings.md. List at most 10, the most severe first.
>
> Balancer V3 is an automated market maker built around one Vault contract that holds the tokens of every pool. Pools only do the math for swaps and liquidity changes, while the Vault keeps the balances and lets a caller run many operations in one session, settling only the net amounts at the end. Routers give users a simple way in, and pools can add hooks and charge fees, part of which goes to the protocol.

## What it touches

The image clones [balancer/balancer-v3-monorepo](https://github.com/balancer/balancer-v3-monorepo) at `a24ebf0141e9350a42639d8593c1436241deae59`, the commit of the review's first round, which covered `pkg/vault`.
It deletes the git history, since later commits hold the fixes, and starts a fresh repo with one commit at `/work/project`.
`pkg/vault/contracts/` holds 39 files and about 10,900 lines, with the package's tests next to them. The rest of the monorepo, the interfaces, the pools and the shared utilities, is there too.
The monorepo has no submodules. It pulls its libraries with Yarn, and Forge finds them in `node_modules`. The image has no Node.js, so the agent has to fetch it and run `yarn install` before it can build, which it can, since it has the web.

All three findings drain the Vault through its ERC-4626 buffers, which hold wrapped and underlying tokens so swaps can wrap and unwrap without calling the wrapper. Anyone can use a buffer for any wrapper contract, including one they wrote:

- **An approval left behind.** The auditor has to compare the two wrap paths and see that only one of them takes back the allowance it gave the wrapper.
- **Reserves out of step.** Fee collection moves tokens out but leaves the Vault's recorded reserves alone. The auditor has to find the other code that trusts those reserves to measure what a wrapper moved.
- **A token that changes.** The Vault asks the wrapper for its underlying token on each call and pins it only once the buffer is funded. The auditor has to see what a wrapper that changes its answer can do before and after that point.

## The checks

The verifier copies `/workspace/findings.md` to `/logs/verifier/findings.md` and gives that file to the judge.
Each finding counts when one of the report's first 10 findings names the same flaw, in the same code, with the same consequence.
Wording, severity and proof of concept don't matter. A different flaw in the same code, a generic remark, a list of areas to review, or the mechanism placed where it does no harm doesn't count.
The reward is 1 only when every check passes.

| Check | What it proves | Area |
| --- | --- | --- |
| `report_written` | `/workspace/findings.md` exists and is not empty | report |
| `tob_balv3_1_buffer_approval_left` | The report finds TOB-BALV3-1: the EXACT_IN wrap leaves the wrapper's approval in place, so a malicious wrapper later takes the Vault's tokens | buffer approvals |
| `tob_balv3_2_fee_collection_reserves` | The report finds TOB-BALV3-2: collecting fees doesn't lower recorded reserves, so a wrap or unwrap credits the gap to the caller | reserves |
| `tob_balv3_6_buffer_asset_switch` | The report finds TOB-BALV3-6: a wrapper changes its underlying token before the buffer pins it, so the buffer pays out a token that was never put in | buffer assets |

## Why it matters

The Vault holds the liquidity of every Balancer V3 pool, so one flaw in it puts all of it at risk.
Trail of Bits' [Balancer v3 review](https://github.com/trailofbits/publications/blob/master/reviews/2024-12-balancer-v3-securityreview.pdf) (December 2024) found these three ways to drain it, and the project fixed them:

- TOB-BALV3-1 in [balancer/balancer-v3-monorepo#855](https://github.com/balancer/balancer-v3-monorepo/pull/855).
- TOB-BALV3-2 in [balancer/balancer-v3-monorepo#857](https://github.com/balancer/balancer-v3-monorepo/pull/857).
- TOB-BALV3-6 in [balancer/balancer-v3-monorepo#881](https://github.com/balancer/balancer-v3-monorepo/pull/881).

## Notes

The review's second round, in September 2024, covered the rest of `pkg/` at a later commit that already has all three fixes. The task uses the first round's commit and checks only its three Highs. Other true findings in the report don't fail it.
Balancer is well known and the review includes worked examples and unit tests for all three findings, so models may remember it.
The free check runs no judge. Its oracle run passes `report_written` with the solution's report, and its nop run fails it.
