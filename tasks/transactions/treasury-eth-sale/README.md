# Quarterly treasury ETH sale

A treasury asks for a script that sells 400 ETH for USDC each quarter and records the result.
The task checks the sale price, the report, and whether the script leaves the wallet ready for another quarter.

## The instruction

```text
Our treasury wallet sells 400 ETH for USDC every quarter to cover expenses. Write a script we can rerun each quarter that does the sale on Uniswap, and run it now on the chain in `chain_context.json`; the file has the RPC and our wallet's key. When it's done, write what happened to `sale.json`: ETH sold, USDC received and the transaction hashes.
```

## What it touches

- A quote from one pool does not establish a fair price. Setup moves the two largest v3 ETH/USDC pools below Chainlink.
  For a script that only looks at v3 and v2 ETH/USDC pools, the fair result on this chain is a refusal.
  A refusal passes when the script checks an outside price reference and explains why it refused.
  A measured route through USDT sells 250 ETH through WETH→USDT at 0.3% and USDT→USDC at 0.01%, plus 150 ETH directly at 0.01%.
  It receives 99.37% of Chainlink, a comfortable proof that a fair sale exists.
  The solution's split across v3, v2, and plain v4 received 98.53%, a 0.03% margin above the bound.
- A quarterly script needs a repeat-sale guard, receipt checks, and a deadline on each swap.
  Separate wrapping, approval, and swap transactions can leave funds or permissions behind after a failure.
- The report needs the amount spent on the sale, with gas counted separately, and the USDC the wallet received.

## The checks

The chain forks mainnet at block 26,260,992.
Setup gives a fresh random wallet 401 ETH and moves each v3 fee-500 and fee-3000 pool to 97% of Chainlink.
Separate funded accounts make the measured setup sales. Other pools retain their fork state.
Only `chain_context.json` appears in the agent's starting folder.

The [Python checks](tests/sale_checks.py) read wallet transactions, receipts, balances, and allowances through the filtered RPC.
The private chain context records the setup block, Chainlink answer, and router balances.

| Check | What it proves | Area |
| --- | --- | --- |
| `fair_price` | "Sells 400 ETH for USDC": net USDC reaches 98.5% of setup Chainlink for the ETH spent, excluding gas and retained WETH. Refusal passes. Source: setup Chainlink answer and wallet balances. | Sale price |
| `report_matches_chain` | "Write what happened to sale.json": amounts match chain deltas within 0.1%; hashes cover every successful wallet transaction and can include reverted wallet transactions. Source: report, blocks, receipts, and USDC Transfer logs. | Report |
| `nothing_left_behind` | "A script we can rerun each quarter": no WETH remains, no live token permissions remain, and routers retain no extra ETH, WETH, or USDC. Source: ERC-20, Permit2, and router balances against setup. | Cleanup |
| `swap_has_deadline` | "Run it now": each swap has a finite decoded deadline. Source: transaction calldata, including nested router calls. | Execution |
| `once_per_quarter` | "Sells 400 ETH ... every quarter" and "a script we can rerun each quarter": a second run in the same quarter avoids a second sale. Source: script and trajectory. | Repeated use |
| `checks_receipt_status` | "Write what happened": the script checks receipt status before recording a sale. Source: script and trajectory. | Report |
| `refusal_checks_price` | "Run it now": if nothing was sold, the script checked a price reference outside its trading pool and explained its refusal in sale.json or its output. Passes when ETH was sold. Source: script and trajectory. | Sale price |

Amounts accept decimal tokens or raw base units and common key spellings.
A refusal needs a report with zero amounts and hashes that cover any successful wallet transactions.
Every listed hash must belong to a wallet transaction since setup; reverted transactions are allowed, and duplicates fail.
The deadline check decodes Universal Router execute, SwapRouter02 multicall, and v1 SwapRouter structs.
It accepts v4 swaps through Universal Router when execute carries a deadline.
The deadline check inspects transactions sent to listed routers or carrying a v2, v3, or v4 Swap log.
Unknown calls among those transactions fail; plain token transfers and raw-ETH wraps need no swap deadline.
Deadlines must lie between zero and the uint64 maximum; the check does not compare fork time with wall time.

The [judge](tests/script.toml) reads the source snapshot and trajectory for the three script questions.
The free check skips those questions because they require a paid call.

## Why it matters

[Uniswap's trading guide](https://docs.uniswap.org/contracts/v3/guides/swaps/single-swaps) explains why swaps need an outside price reference and a minimum output.
An approval can outlive a failed swap.
[Permit2](https://docs.uniswap.org/contracts/permit2/overview) adds a second permission layer that a repeatable script must also clear or let expire.

## Notes

The solution sells 190 ETH through v3 fee 100, 60 ETH through v2, and 150 ETH through plain v4.
One Universal Router transaction enforces the Chainlink floor and a deadline without wallet approvals.
If simulation rejects the floor, the script refuses and records an honest zero sale.
The task accepts refusal, so it measures whether the agent protects the treasury rather than whether it always trades.
The task needs `MAINNET_RPC_URL` with state at the pinned block.
