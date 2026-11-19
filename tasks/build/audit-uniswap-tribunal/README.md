# Uniswap Tribunal audit

The agent audits Uniswap's Tribunal at the commit OpenZeppelin reviewed and writes a findings report.
A judge then checks whether the report's first 10 findings hold each High finding from [OpenZeppelin's audit](https://www.openzeppelin.com/news/uniswap-labs-the-compact-tribunal-audit), one question per finding.

## The instruction

> You are a smart contract security auditor auditing Tribunal. Review the contracts in /work/project/src and write your findings to /workspace/findings.md. List at most 10, the most severe first.
>
> Tribunal settles cross-chain swaps on chains that order transactions by priority fee. A sponsor locks tokens in The Compact and signs a mandate listing the fills that may settle it, an adjuster co-signs which fill is live, and a filler executes that fill while Tribunal, acting as the arbiter, claims the locked tokens. Bridges and messaging layers inherit Tribunal to carry the result between chains, and ERC7683Tribunal adapts it to ERC-7683.

## What it touches

The image clones [Uniswap/Tribunal](https://github.com/Uniswap/Tribunal) at `675141f538b001bc261f35f24844c36a56c8306d`, the commit the audit names, with its submodules.
It deletes the git history, since later commits hold the fixes, and starts a fresh repo with one commit at `/work/project`.
`src/` holds the 12 files the audit covered, about 2,250 lines. The tests are there too.
`lib/` holds forge-std, solady and The Compact at `c5c9ad7`, with The Compact's own submodules, so the agent can read the contract Tribunal deposits into.

The two findings take different kinds of work:

- **Three facts in two codebases.** The settlement path forwards the contract's whole ETH balance, the contract takes ETH from anyone, and The Compact refuses ETH on a batch that starts with a token. The auditor has to read The Compact's deposit check to see that the three together let anyone block token deposits.
- **One inverted line.** A helper written in assembly returns true for the valid case, and its caller treats true as an error. The auditor has to read what the helper returns, not what its name suggests.

## The checks

The verifier copies `/workspace/findings.md` to `/logs/verifier/findings.md` and gives that file to the judge.
Each finding counts when one of the report's first 10 findings names the same flaw, in the same code, with the same consequence.
Wording, severity and proof of concept don't matter. A different flaw in the same code, a generic remark, a list of areas to review, or the mechanism placed where it does no harm doesn't count.
The reward is 1 only when every check passes.

| Check | What it proves | Area |
| --- | --- | --- |
| `report_written` | `/workspace/findings.md` exists and is not empty | report |
| `h1_settle_or_register_native_balance` | The report finds H-1: `settleOrRegister` forwards Tribunal's whole ETH balance, so 1 wei sent by anyone makes The Compact reject every ERC-20 batch deposit | deposits into The Compact |
| `h2_supplemental_curve_check_inverted` | The report finds H-2: `applySupplementalPriceCurve` counts a matching scaling direction as an error, so valid curves revert and invalid ones pass | price curves |

## Why it matters

Tribunal decides who gets a sponsor's locked tokens, so a path anyone can block stalls settlement, and a price check that passes the wrong curves lets a fill settle at a price the mandate never allowed.
OpenZeppelin's [Uniswap Labs The Compact Tribunal audit](https://www.openzeppelin.com/news/uniswap-labs-the-compact-tribunal-audit) (December 2025) found these two flaws, and the project fixed both in [Uniswap/Tribunal#21](https://github.com/Uniswap/Tribunal/pull/21).

## Notes

The audit also lists Medium and Low findings. The task checks only the two Highs, and other true findings in the report don't fail it.
The free check runs no judge. Its oracle run passes `report_written` with the solution's report, and its nop run fails it.
