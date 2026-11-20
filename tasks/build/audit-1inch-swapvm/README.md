# 1inch SwapVM audit

The agent audits 1inch's SwapVM at the commit OpenZeppelin reviewed and writes a findings report.
A judge then checks whether the report's first 10 findings hold each Critical and High finding from [OpenZeppelin's audit](https://www.openzeppelin.com/news/1inch-aqua-and-swapvm-mvp-v1.0-audit), one question per finding.

## The instruction

> You are a smart contract security auditor auditing SwapVM. Review the contracts in /work/project/src and write your findings to /workspace/findings.md. List at most 10, the most severe first.
>
> SwapVM is 1inch's virtual machine for token swaps. A maker writes a program, bytecode that chains small instructions for balances, pricing curves, fees and limits, and either signs it or ships it through Aqua, 1inch's shared liquidity layer where makers keep their tokens in their own wallets. A taker runs the maker's program to work out the swap amounts and settle the trade, and a strategy contract builds a ready-made AMM program from these instructions.

## What it touches

The image clones [1inch/swap-vm](https://github.com/1inch/swap-vm) at `60172ba83234bacb793c11564fed3a806b6d3388`, the commit the audit names.
It deletes the git history, since later commits hold the fixes, and starts a fresh repo with one commit at `/work/project`.
`src/` holds 42 files, about 3,800 lines. The audit's SwapVM scope is 16 of them, and all five findings sit in `src/`. The tests are there too.
The audit also covered Aqua and 1inch's solidity-utils, which SwapVM imports. The project pulls them, OpenZeppelin and forge-std with npm. The image has Node.js 22 with npm, and Yarn and pnpm through Corepack, but it does not install the project's packages, so `forge build` fails until the agent runs `npm install`. It has the web.

The findings take two kinds of work:

- **Curve math.** The pegged curve is solved in closed form. The auditor has to see where the formula cancels to nothing for small curve settings, and that its balances are normalized by token order while the swap runs by direction.
- **One number for many pairs.** Concentrated liquidity keeps one value per order. The auditor has to see that an order can hold three tokens and that each pair overwrites what the others read.
- **Instructions that wrap each other.** Each instruction runs the rest of the program inside it, and fee instructions change the swap amounts and put them back. The auditor has to follow what the outer instruction records after a protocol fee has already left the maker, for concentrated liquidity on the output side and for stored balances on the input side.

## The checks

The verifier copies `/workspace/findings.md` to `/logs/verifier/findings.md` and gives that file to the judge.
Each finding counts when one of the report's first 10 findings names the same flaw, in the same code, with the same consequence.
Wording, severity and proof of concept don't matter. A different flaw in the same code, a generic remark, a list of areas to review, or the mechanism placed where it does no harm doesn't count.
The reward is 1 only when every check passes.

| Check | What it proves | Area |
| --- | --- | --- |
| `report_written` | `/workspace/findings.md` exists and is not empty | report |
| `c1_pegged_solve_precision` | The report finds C-1: the pegged curve's quadratic solver cancels to nothing for small curve settings, so the maker pays out more than the curve allows | curve math |
| `c2_concentrate_shared_liquidity` | The report finds C-2: a multi-token concentrated order keeps one liquidity value that each pair overwrites, so a three-swap cycle makes a profit | concentrated liquidity |
| `c3_pegged_axis_mismatch` | The report finds C-3: the pegged curve normalizes balances by token order instead of swap direction, so reverse swaps pay out far too much | curve math |
| `h1_concentrate_protocol_fee_out` | The report finds H-1: concentrated liquidity is recorded without the output-side protocol fee that left the maker | fee accounting |
| `h2_dynamic_balances_protocol_fee_in` | The report finds H-2: stored dynamic balances count the gross input although an input-side protocol fee was paid out at once | fee accounting |

## Why it matters

Makers' funds back every quote SwapVM gives, so a curve that pays out too much or a record that drifts from the real balances moves money from makers to takers.
OpenZeppelin's [1inch Aqua and SwapVM MVP v1.0 audit](https://www.openzeppelin.com/news/1inch-aqua-and-swapvm-mvp-v1.0-audit) found these five flaws, and the project fixed them:

- C-1 in [1inch/swap-vm#67](https://github.com/1inch/swap-vm/pull/67).
- C-2 in [1inch/swap-vm#82](https://github.com/1inch/swap-vm/pull/82).
- C-3 in [1inch/swap-vm#68](https://github.com/1inch/swap-vm/pull/68).
- H-1 and H-2 in [1inch/swap-vm#75](https://github.com/1inch/swap-vm/pull/75).

## Notes

The audit also lists Medium and Low findings. The task checks only the Criticals and Highs, and other true findings in the report don't fail it.
H-1 and H-2 both come from a protocol fee leaving the maker inside another instruction, and the audit's Mediums include two more of the same family: a taker paying the fee twice in Aqua's push mode, and the decay instruction storing the pre-fee amount. Each question says which record and which fee it means.
The free check runs no judge. Its oracle run passes `report_written` with the solution's report, and its nop run fails it.
