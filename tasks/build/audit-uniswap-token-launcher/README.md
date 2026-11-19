# Uniswap Token Launcher audit

The agent audits Uniswap's Token Launcher contracts at the commit OpenZeppelin reviewed and writes a findings report.
A judge then checks whether the report's first 10 findings hold the Critical and the High finding from [OpenZeppelin's audit](https://www.openzeppelin.com/news/uniswap-token-launcher-audit) that this task uses, one question per finding.

## The instruction

> You are a smart contract security auditor auditing Token Launcher. Review the contracts in /work/project/src and write your findings to /workspace/findings.md. List at most 10, the most severe first.
>
> Token Launcher hands out a new or existing token through pluggable distribution strategies built on Uniswap v4. TokenLauncher deploys the chosen strategy from its factory and sends it the tokens. The main strategy, LBPStrategyBasic, sells part of the supply in a separate auction contract to find a price, then opens a Uniswap v4 pool at that price with the rest, acting as the pool's hook until then. A Merkle claim strategy covers airdrops.

## What it touches

The image clones [Uniswap/token-launcher](https://github.com/Uniswap/token-launcher) (now `Uniswap/liquidity-launcher`) at `9eff2a7612e99e9a072e128be529be2ed19be313`, the commit the audit names, with its ten submodules and their own submodules at their pinned commits.
One of them is the auction itself, `lib/twap-auction`, from `Uniswap/twap-auction` (now `continuous-clearing-auction`). The audit read it as a reference but did not review it.
Another is the Optimism monorepo, which makes the image large.
It deletes the git history, since later commits hold the fixes, and starts a fresh repo with one commit at `/work/project`.
`src/` holds 28 files, about 1,500 lines, all of them in the audit's scope. The tests are there too.

Both findings sit where LBPStrategyBasic hands its tokens to the auction and waits for the auction to call back:

- **The unhappy path.** The reserved tokens leave the strategy only after a callback the auction makes when it succeeds. The auditor has to read the auction to learn when it makes that call, and then look for any way out of the strategy when it doesn't.
- **Settings passed through unread.** The strategy forwards the auction parameters as opaque bytes. The auditor has to decode them in the auction's code, see which recipients they set, and work out what happens when those recipients are not the strategy.

## The checks

The verifier copies `/workspace/findings.md` to `/logs/verifier/findings.md` and gives that file to the judge.
Each finding counts when one of the report's first 10 findings names the same flaw, in the same code, with the same consequence.
Wording, severity and proof of concept don't matter. A different flaw in the same code, a generic remark, a list of areas to review, or the mechanism placed where it does no harm doesn't count.
The reward is 1 only when every check passes.

| Check | What it proves | Area |
| --- | --- | --- |
| `report_written` | `/workspace/findings.md` exists and is not empty | report |
| `c1_reserve_stuck_without_graduation` | The report finds C-1: when the auction fails, it never calls `validate()`, and the tokens reserved for the pool are locked in LBPStrategyBasic | failed auctions |
| `h1_unchecked_auction_recipients` | The report finds H-1: nothing checks the auction's funds and token recipients, so a wrong value sends the raised money elsewhere or locks tokens in the strategy, even after a successful auction | auction settings |

## Why it matters

A launch strategy holds the new token's supply for the whole sale, so a path it never planned for can lock a launch's liquidity for good.
OpenZeppelin's [Uniswap Token Launcher audit](https://www.openzeppelin.com/news/uniswap-token-launcher-audit) (September 2026) found both flaws, and the project fixed them:

- C-1 in [Uniswap/token-launcher#51](https://github.com/Uniswap/token-launcher/pull/51), which adds sweep functions.
- H-1 in [Uniswap/token-launcher#49](https://github.com/Uniswap/token-launcher/pull/49), which checks the funds recipient.

## Notes

The audit's other High is not checked. It is a mismatch between an interface and its implementation in a pull request reviewed before the main commit, a deploy-time bug rather than an attack.
The audit also lists Medium and Low findings, and other true findings in the report don't fail the task.
In an earlier trial setup the auction submodule was empty, so the agent could not read the auction's code. This image fills every submodule.
`forge build` compiles every contract, then forge's lint step stops on a script path it can't find and exits with an error. The tests fork mainnet and need a `FORK_URL`, which the image doesn't set.
The free check runs no judge. Its oracle run passes `report_written` with the solution's report, and its nop run fails it.
