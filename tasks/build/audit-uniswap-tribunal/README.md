# Uniswap Tribunal audit

Uniswap Labs hands a security auditor Tribunal, the contract that settles cross-chain swaps by claiming the tokens a sponsor locked in The Compact.
The agent is that auditor: it gets Tribunal at the commit OpenZeppelin reviewed and writes up what it finds.
A judge then checks whether its report holds the two High findings from [OpenZeppelin's audit](https://www.openzeppelin.com/news/uniswap-labs-the-compact-tribunal-audit).

## The instruction

> You are a smart contract security auditor auditing Tribunal. Review the contracts in /work/project/src and write your findings to /workspace/findings.md. List at most 10, the most severe first.
>
> Tribunal settles cross-chain swaps on chains that order transactions by priority fee. A sponsor locks tokens in The Compact and signs a mandate listing the fills that may settle it, an adjuster co-signs which fill is live, and a filler executes that fill while Tribunal, acting as the arbiter, claims the locked tokens. Bridges and messaging layers inherit Tribunal to carry the result between chains, and ERC7683Tribunal adapts it to ERC-7683.

## What it touches

The instruction names Tribunal and The Compact and says nothing about where to look.
One finding needs The Compact's code as well as Tribunal's, and the other is one line in Tribunal's price-curve code.

- **Three facts in two codebases.** The settlement path forwards the contract's whole ETH balance, the contract takes ETH from anyone, and The Compact refuses ETH on a batch that starts with a token. The auditor has to read The Compact's deposit check to see that the three together let anyone block token deposits.
- **One inverted line.** A helper written in assembly returns true for the valid case, and its caller treats true as an error. The auditor has to read what the helper returns, not what its name suggests.

## The checks

The agent starts with [Uniswap/Tribunal](https://github.com/Uniswap/Tribunal) at `675141f538b001bc261f35f24844c36a56c8306d` in `/work/project`, with its submodules, as one commit with no history, since later commits hold the fixes.
`src/` holds the 12 files the audit covered, about 2,250 lines, and the tests are there too.
`lib/` holds forge-std, solady and The Compact at `c5c9ad7`, with The Compact's own submodules, so the agent can read the contract Tribunal deposits into.
The agent writes `/workspace/findings.md`, and the judge reads only that file.
A finding counts when one of the report's first 10 findings describes the same flaw, in the same code, with the same consequence.
Wording, severity and proof of concept don't matter. A different flaw in the same code, a generic remark or a list of areas to review doesn't count.
The task gives partial credit: the reward is how many of the two findings the report found, divided by two. `report_written` carries no weight.

| Check | What it proves | Area |
| --- | --- | --- |
| `report_written` | `/workspace/findings.md` exists and is not empty | report |
| `h1_settle_or_register_native_balance` | The report finds H-1: `settleOrRegister` forwards Tribunal's whole ETH balance, so 1 wei sent by anyone makes The Compact reject every ERC-20 batch deposit | deposits into The Compact |
| `h2_supplemental_curve_check_inverted` | The report finds H-2: `applySupplementalPriceCurve` counts a matching scaling direction as an error, so valid curves revert and invalid ones pass | price curves |

## Why it matters

This is one of 16 audit tasks picked from public OpenZeppelin and Trail of Bits reports. [Issue #109](https://github.com/BuidlGuidl/ethevals/issues/109) has the full list and how we picked them.
Tribunal is in because one finding needs three facts seen together, one of them in The Compact's code, and the other is one line in the caller of an assembly helper that is easy to read past.

Code that trusts its own ETH balance can be broken by anyone who sends it some.
In July 2019 Edgeware's lockdrop asserted that each new lock contract's balance equalled the ETH sent with the call.
Anyone could send some wei to the next lock's address first and make every later lock fail, as [Trail of Bits explains](https://blog.trailofbits.com/2019/07/03/avoiding-smart-contract-gridlock-with-slither).
It says as much as $900 million worth of Ether may have been processed by that contract, and the fix replaced `==` with `>=`.

A condition that is wrong by one character reads almost the same as the right one.
When Compound executed Proposal 62 on 29 September 2021, users in some markets could claim far more COMP than intended, per [Compound's own update](https://compound.substack.com/p/compound-treasury-updates-comp-bug).
The code used `>` where it should have used `>=`, per [The Register](https://www.theregister.com/2021/10/01/compound_crypto_bug/). Compound's update counts 163k COMP wrongly claimed and returned, and about 200k still outstanding.
Tribunal's H-2 is the same size: its [fix](https://github.com/Uniswap/Tribunal/commit/36c31cafa191104718e166bc1f2cbe2fdab0bc6d) adds one `!` in front of the helper's result.

These two were caught in review.
OpenZeppelin reported them in its [Uniswap Labs The Compact Tribunal audit](https://www.openzeppelin.com/news/uniswap-labs-the-compact-tribunal-audit) (December 2025), and the project fixed both in [Uniswap/Tribunal#21](https://github.com/Uniswap/Tribunal/pull/21).

## Notes

- The audit also lists Medium and Low findings. The task checks only the two Highs, and other true findings in the report don't fail it.
- Tribunal is a Foundry project whose libraries all come from the submodules in `lib/`, which the image fills, so it needs no package install. The agent has the web.
- The free check runs no judge. Its oracle run passes `report_written` with the solution's report, and its nop run fails it.
