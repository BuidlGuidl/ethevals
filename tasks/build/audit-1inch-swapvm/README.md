# 1inch SwapVM audit

1inch hands a security auditor SwapVM, its virtual machine where each maker writes a small program that prices its swaps.
The agent is that auditor: it gets the code at the commit OpenZeppelin reviewed and writes up what it finds.
A judge then checks whether its report holds the three Critical and two High findings from [OpenZeppelin's audit](https://www.openzeppelin.com/news/1inch-aqua-and-swapvm-mvp-v1.0-audit).

## The instruction

> You are a smart contract security auditor auditing SwapVM. Review the contracts in /work/project/src and write your findings to /workspace/findings.md. List at most 10, the most severe first.
>
> SwapVM is 1inch's virtual machine for token swaps. A maker writes a program, bytecode that chains small instructions for balances, pricing curves, fees and limits, and either signs it or ships it through Aqua, 1inch's shared liquidity layer where makers keep their tokens in their own wallets. A taker runs the maker's program to work out the swap amounts and settle the trade, and a strategy contract builds a ready-made AMM program from these instructions.

## What it touches

The instruction describes SwapVM and Aqua and says nothing about where to look.
Three findings are in the curve math, and two are in what an instruction records after a protocol fee has left the maker.
Each instruction runs the rest of the program inside it, and fee instructions change the swap amounts and put them back, so the auditor has to follow amounts from one instruction into the next.

- **A formula that cancels.** The pegged curve is solved in closed form. The auditor has to see where the formula cancels to nothing for small curve settings.
- **One number for many pairs.** Concentrated liquidity keeps one value per order. The auditor has to see that an order can hold three tokens and that each pair overwrites what the others read.
- **Order where it should be direction.** The pegged curve normalizes its balances by token order, while the swap runs by direction. The auditor has to see what that does to a swap the other way.
- **A fee gone on the way out.** The auditor has to follow what concentrated liquidity records after an output-side protocol fee has already left the maker.
- **A fee gone on the way in.** The auditor has to follow what stored dynamic balances record after an input-side protocol fee was paid straight out.

## The checks

The agent starts with [1inch/swap-vm](https://github.com/1inch/swap-vm) at `60172ba83234bacb793c11564fed3a806b6d3388` in `/work/project`, as one commit with no history, since later commits hold the fixes.
`src/` holds 42 files, about 3,800 lines. The audit's SwapVM scope is 16 of them, and all five findings sit in `src/`. The tests are there too.
The agent writes `/workspace/findings.md`, and the judge reads only that file.
A finding counts when one of the report's first 10 findings describes the same flaw, in the same code, with the same consequence.
Wording, severity and proof of concept don't matter. A different flaw in the same code, a generic remark or a list of areas to review doesn't count.
The task gives partial credit: the reward is how many of the five findings the report found, divided by five. `report_written` carries no weight.

| Check | What it proves | Area |
| --- | --- | --- |
| `report_written` | `/workspace/findings.md` exists and is not empty | report |
| `c1_pegged_solve_precision` | The report finds C-1: the pegged curve's quadratic solver cancels to nothing for small curve settings, so the maker pays out more than the curve allows | curve math |
| `c2_concentrate_shared_liquidity` | The report finds C-2: a multi-token concentrated order keeps one liquidity value that each pair overwrites, so a three-swap cycle makes a profit | concentrated liquidity |
| `c3_pegged_axis_mismatch` | The report finds C-3: the pegged curve normalizes balances by token order instead of swap direction, so reverse swaps pay out far too much | curve math |
| `h1_concentrate_protocol_fee_out` | The report finds H-1: concentrated liquidity is recorded without the output-side protocol fee that left the maker | fee accounting |
| `h2_dynamic_balances_protocol_fee_in` | The report finds H-2: stored dynamic balances count the gross input although an input-side protocol fee was paid out at once | fee accounting |

## Why it matters

This is one of 16 audit tasks picked from public OpenZeppelin and Trail of Bits reports. [Issue #109](https://github.com/BuidlGuidl/ethevals/issues/109) has the full list and how we picked them.
SwapVM is in because its findings are AMM math the auditor has to model, and with five of them there's room to tell strong agents apart.

A small slip in an AMM's curve math is enough to drain it.
On 23 November 2023 attackers took over $48M from KyberSwap pools on several chains, per [BlockSec's analysis](https://blocksec.com/blog/yet-another-tragedy-of-precision-loss-an-in-depth-analysis-of-the-kyber-swap-incident-1).
The root cause was a value rounded the wrong way in the pool's reinvestment math, which let it count one tick's liquidity twice.
SwapVM's C-1 is the same kind of slip: precision lost in the pegged curve's solver lets a swap take more than the curve allows.

A fee that leaves without lowering the recorded balance makes the books promise more than the maker holds.
For H-1, OpenZeppelin writes that "recorded liquidity diverges from actual reserves, causing the pool to promise swaps it cannot fulfill."
Trail of Bits found the same slip in Balancer V3's Vault in 2024: fees counted in the Vault's reserves were collected without lowering those reserves, a High it titled "Lack of reserve updates when collecting fees allows anyone to drain the Vault" ([TOB-BALV3-2](https://github.com/trailofbits/publications/blob/master/reviews/2024-12-balancer-v3-securityreview.pdf)).
We found no public theft from a fee left in a recorded balance.
We found none either for C-2 and C-3: one liquidity value shared by every pair of a multi-token order, and a curve that orders its balances by token instead of by swap direction. Those two rest on why the engagement was picked.

These five were caught in review.
OpenZeppelin reported them in its [1inch Aqua and SwapVM MVP v1.0 audit](https://www.openzeppelin.com/news/1inch-aqua-and-swapvm-mvp-v1.0-audit) (July 2026), and the project fixed them:

- C-1 in [1inch/swap-vm#67](https://github.com/1inch/swap-vm/pull/67).
- C-2 in [1inch/swap-vm#82](https://github.com/1inch/swap-vm/pull/82).
- C-3 in [1inch/swap-vm#68](https://github.com/1inch/swap-vm/pull/68).
- H-1 and H-2 in [1inch/swap-vm#75](https://github.com/1inch/swap-vm/pull/75).

## Notes

- The audit also lists Medium and Low findings. The task checks only the Criticals and Highs, and other true findings in the report don't fail it.
- H-1 and H-2 both come from a protocol fee leaving the maker inside another instruction, and the audit's Mediums include two more of the same family: a taker paying the fee twice in Aqua's push mode, and the decay instruction storing the pre-fee amount. Each question says which record and which fee it means.
- The audit also covered Aqua and 1inch's solidity-utils, which SwapVM imports. The project pulls them, OpenZeppelin and forge-std with npm. The image has Node.js 22 with npm, and Yarn and pnpm through Corepack, but not the project's packages, so `forge build` fails until the agent runs `npm install`. It has the web.
- The free check runs no judge. Its oracle run passes `report_written` with the solution's report, and its nop run fails it.
