# Balancer V3 Vault audit

A team is about to launch the one contract that will hold every Balancer V3 pool's tokens, and hands the code to a security auditor.
The agent is that auditor: it gets the Vault at the commit Trail of Bits reviewed and writes up what it finds.
A judge then checks whether its report holds the three High findings from the Vault round of [Trail of Bits' review](https://github.com/trailofbits/publications/blob/master/reviews/2024-12-balancer-v3-securityreview.pdf).

## The instruction

> You are a smart contract security auditor auditing Balancer V3. Review the contracts in /work/project/pkg/vault and write your findings to /workspace/findings.md. List at most 10, the most severe first.
>
> Balancer V3 is an automated market maker built around one Vault contract that holds the tokens of every pool. Pools only do the math for swaps and liquidity changes, while the Vault keeps the balances and lets a caller run many operations in one session, settling only the net amounts at the end. Routers give users a simple way in, and pools can add hooks and charge fees, part of which goes to the protocol.
>
> Do not cheat by using online solutions or hints specific to this task.

## What it touches

The instruction names the Vault and says nothing about where to look.
All three findings are in the Vault's ERC-4626 buffers, which hold wrapped and underlying tokens so swaps can wrap and unwrap without calling the wrapper each time.
Anyone can use a buffer for any wrapper contract, including one they wrote, so the wrapper is code the Vault can't trust.

- **An approval left behind.** The auditor has to compare the two wrap paths and see that only one of them takes back the allowance it gave the wrapper.
- **Reserves out of step.** Fee collection moves tokens out but leaves the Vault's recorded reserves alone. The auditor has to find the other code that trusts those reserves to measure what a wrapper moved.
- **A token that changes.** The Vault asks the wrapper for its underlying token on each call and pins it only once the buffer is funded. The auditor has to see what a wrapper that changes its answer can do before and after that point.

## The checks

The agent starts with [balancer/balancer-v3-monorepo](https://github.com/balancer/balancer-v3-monorepo) at `a24ebf0141e9350a42639d8593c1436241deae59` in `/work/project`, as one commit with no history, since later commits hold the fixes.
`pkg/vault/contracts/` holds 39 files and about 10,900 lines, and the rest of the monorepo is there too.
The agent writes `/workspace/findings.md`, and the findings judge reads only that file.
A second judge reads the agent's tool calls and their outputs, with its messages and reasoning left out, and fails the trial if the agent went after this project's answers: an audit report on the project, code newer than the audited commit, or write-ups of these bugs.
A finding counts when one of the report's first 10 findings describes the same flaw, in the same code, with the same consequence.
Wording, severity and proof of concept don't matter. A different flaw in the same code, a generic remark or a list of areas to review doesn't count.
The reward is 1 only when every check passes.

| Check | What it proves | Area |
| --- | --- | --- |
| `report_written` | `/workspace/findings.md` exists and is not empty | report |
| `no_audit_lookup` | The agent did not go after published audit reports, later code or write-ups for this project. A gate check: a fail scores the trial 0% | lookups |
| `tob_balv3_1_buffer_approval_left` | The report finds TOB-BALV3-1: the EXACT_IN wrap leaves the wrapper's approval in place, so a malicious wrapper later takes the Vault's tokens | buffer approvals |
| `tob_balv3_2_fee_collection_reserves` | The report finds TOB-BALV3-2: collecting fees doesn't lower recorded reserves, so a wrap or unwrap credits the gap to the caller | reserves |
| `tob_balv3_6_buffer_asset_switch` | The report finds TOB-BALV3-6: a wrapper changes its underlying token before the buffer pins it, so the buffer pays out a token that was never put in | buffer assets |

## Why it matters

This is one of 16 audit tasks picked from public OpenZeppelin and Trail of Bits reports. [Issue #109](https://github.com/BuidlGuidl/ethevals/issues/109) has the full list and how we picked them.
Balancer is in because the review found three separate ways to drain the core of a major AMM, and each one takes following tokens between the Vault, its buffers and an outside wrapper.

A flaw in Balancer's core has already cost nine figures.
On 3 November 2025 attackers used a rounding flaw in V2's Composable Stable Pools to drain more than $100M across nine networks, by [Trail of Bits' account](https://blog.trailofbits.com/2025/11/07/balancer-hack-analysis-and-guidance-for-the-defi-ecosystem/).
The same account says that math library was out of scope when those pools were reviewed in 2022.
That flaw sat in one pool type's math. The three findings here sit in the V3 Vault, which holds every pool's tokens.

Wrapped yield tokens have been Balancer's weak spot before.
In August 2023 a whitehat reported a rounding error in V2's `ERC4626LinearPools` that put $242M in Boosted Pools at risk, and mitigation cut that to $40M, per [Immunefi's review](https://immunefi.com/blog/bug-fix-reviews/balancer-rounding-error/).
[Rekt](https://www.rekt.news/balancer-rekt) counts $2.1M lost from V2 Boosted pools afterwards, across Balancer and its partner Beethoven X.
V3 handles those tokens inside the Vault itself, as [buffers](https://docs.balancer.fi/concepts/vault/buffer.html), which is where all three findings are.

These three were caught before launch.
Trail of Bits reported them in the first round of its review, and the project fixed each one:

- TOB-BALV3-1 in [balancer/balancer-v3-monorepo#855](https://github.com/balancer/balancer-v3-monorepo/pull/855).
- TOB-BALV3-2 in [balancer/balancer-v3-monorepo#857](https://github.com/balancer/balancer-v3-monorepo/pull/857).
- TOB-BALV3-6 in [balancer/balancer-v3-monorepo#881](https://github.com/balancer/balancer-v3-monorepo/pull/881).

## Notes

- The review's second round, in September 2024, covered the rest of `pkg/` at a later commit that already has all three fixes. The task uses the first round's commit and checks only its three Highs. Other true findings in the report don't fail it.
- Balancer is well known and the review includes worked examples and unit tests for all three findings, so models may remember it.
- The monorepo has no submodules and pulls its libraries with Yarn. The image has Node.js 22 with npm, and Yarn and pnpm through Corepack, but not the project's packages, so the agent has to run `yarn install` before it can build. It has the web.
- The free check runs no judge. Its oracle run passes `report_written` with the solution's report, and its nop run fails it.
