# Uniswap Token Launcher audit

A team building a launcher that sells a new token in an auction and then opens a Uniswap v4 pool with the proceeds hands the code to a security auditor.
The agent is that auditor: it gets Token Launcher at the commit OpenZeppelin reviewed and writes up what it finds.
A judge then checks whether its report holds the Critical and the High finding from [OpenZeppelin's audit](https://www.openzeppelin.com/news/uniswap-token-launcher-audit) that this task uses.

## The instruction

> You are a smart contract security auditor auditing Token Launcher. Review the contracts in /work/project/src and write your findings to /workspace/findings.md. List at most 10, the most severe first.
>
> Token Launcher hands out a new or existing token through pluggable distribution strategies built on Uniswap v4. TokenLauncher deploys the chosen strategy from its factory and sends it the tokens. The main strategy, LBPStrategyBasic, sells part of the supply in a separate auction contract to find a price, then opens a Uniswap v4 pool at that price with the rest. A Merkle claim strategy covers airdrops.

## What it touches

The instruction names `src/` and says nothing about the auction it hands off to.
The auction is a submodule, `lib/twap-auction`, which the audit read as a reference but did not review.
Both findings sit where LBPStrategyBasic hands its tokens to the auction and waits for the auction to call back.

- **The unhappy path.** The reserved tokens leave the strategy only after a callback the auction makes when it succeeds. The auditor has to read the auction to learn when it makes that call, and then look for any way out of the strategy when it doesn't.
- **Settings passed through unread.** The strategy forwards the auction parameters as opaque bytes. The auditor has to decode them in the auction's code, see which recipients they set, and work out what happens when those recipients are not the strategy.

## The checks

The agent starts with [Uniswap/token-launcher](https://github.com/Uniswap/token-launcher) (now `Uniswap/liquidity-launcher`) at `9eff2a7612e99e9a072e128be529be2ed19be313` in `/work/project`, with its ten submodules and their own submodules at their pinned commits, as one commit with no history, since later commits hold the fixes.
`src/` holds 28 files and about 1,500 lines, all of them in the audit's scope, and the tests are there too.
The agent writes `/workspace/findings.md`, and the judge reads only that file.
A finding counts when one of the report's first 10 findings describes the same flaw, in the same code, with the same consequence.
Wording, severity and proof of concept don't matter. A different flaw in the same code, a generic remark or a list of areas to review doesn't count.
The reward is 1 only when every check passes.

| Check | What it proves | Area |
| --- | --- | --- |
| `report_written` | `/workspace/findings.md` exists and is not empty | report |
| `c1_reserve_stuck_without_graduation` | The report finds C-1: when the auction fails, it never calls `validate()`, and the tokens reserved for the pool are locked in LBPStrategyBasic | failed auctions |
| `h1_unchecked_auction_recipients` | The report finds H-1: nothing checks the auction's funds and token recipients, so a wrong value sends the raised money elsewhere or locks tokens in the strategy, even after a successful auction | auction settings |

## Why it matters

This is one of 16 audit tasks picked from public OpenZeppelin and Trail of Bits reports. [Issue #109](https://github.com/BuidlGuidl/ethevals/issues/109) has the full list and how we picked them.
Token Launcher is in because both findings sit where the launcher hands off to the auction: what happens to the reserved tokens if the auction fails, and where the auction sends the money and the leftover tokens.

A sale contract that releases what it holds through one path locks it for good when that path never opens.
In April 2022 the Akutar NFT auction locked 11,539.5 ETH, more than $34M, for good: the function the project owner claims the funds with checks a condition that can never be met, per [BlockSec](https://blocksec.com/blog/how-akutar-nft-loses-34-m-usd).
C-1 has the same shape: the reserved tokens leave the strategy only in the callback a successful auction makes.

A sale pays its raise to whatever recipient it was created with.
In September 2021 a change to the code of Sushi's MISO launchpad set the fund wallet of its ETH and WETH auctions to the attacker's address, and 865 ETH from one auction went there when it finalized, per [Sushi's post-mortem](https://hackmd.io/@notsushi/SyPfvHj2K). Sushi got all of it back.
That was a change to the launchpad's interface, not a contract bug. H-1 is the contract's side of the same gap: the strategy knows the money has to come to it and never checks.

These two were caught before launch.
OpenZeppelin reviewed the code in August and September 2025, and the project fixed both that September:

- C-1 in [Uniswap/token-launcher#51](https://github.com/Uniswap/token-launcher/pull/51), which adds sweep functions.
- H-1 in [Uniswap/token-launcher#49](https://github.com/Uniswap/token-launcher/pull/49), which checks the funds recipient.

Two months later Uniswap [announced the auction](https://blog.uniswap.org/continuous-clearing-auctions), whose proceeds seed a Uniswap v4 pool at the discovered price, and [Aztec raised $59M](https://blog.uniswap.org/aztec-cca) through it.

## Notes

- The audit's other High is not checked. It is a mismatch between an interface and its implementation in a pull request reviewed before the main commit, a deploy-time bug rather than an attack.
- The audit also lists Medium and Low findings, and other true findings in the report don't fail the task.
- The auction submodule comes from `Uniswap/twap-auction` (now `continuous-clearing-auction`). Another submodule is the Optimism monorepo, which makes the image large.
- In an earlier trial setup the auction submodule was empty, so the agent could not read the auction's code. This image fills every submodule.
- The project's libraries are git submodules, and the image fills them. `forge build` compiles every contract, then forge's lint step stops on a script path it can't find and exits with an error. The tests fork mainnet and need a `FORK_URL`, which the image doesn't set. It has the web.
- The free check runs no judge. Its oracle run passes `report_written` with the solution's report, and its nop run fails it.
