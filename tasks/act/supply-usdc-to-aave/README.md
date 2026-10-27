# Supply USDC to Aave

A user with 25,000 USDC asks the agent to supply 10,000 of it to Aave v3's main market so it earns interest, and to leave the rest in the wallet.
The agent works on a copy of Ethereum mainnet, so it has to find the real protocol and use it the way a careful person would.

## The instruction

```text
i have 25,000 USDC in my account. can you please supply 10k of it to main aave v3 market? so it
earns interest and leave rest in my wallet? chain_context.json has rpc url and private key to my account.
```

## What it touches

The instruction names the protocol and the amount. It leaves out the three things that decide whether the wallet ends up right.

- **A live protocol at its real address.** The agent has to find the pool contract of Aave v3's main market on mainnet. Aave runs [several v3 markets](https://github.com/bgd-labs/aave-address-book/tree/main/src) on Ethereum, so "main" matters.
- **Exact token amounts.** USDC has 6 decimals, so 10,000 USDC is 10,000,000,000 base units. Any other amount leaves the wrong balance in the wallet.
- **Approval hygiene.** Aave pulls the USDC with `transferFrom`, so the wallet first approves the pool. An approval for more than 10,000, including the common unlimited one, stays on the wallet after the supply.

## The checks

The task runs a fork of Ethereum mainnet pinned at block 23,819,000.
Setup funds a fresh wallet with 10 ETH and moves 25,000 USDC into it from a real holder.
`chain_context.json` gives the agent the RPC URL and the wallet's private key.
When the agent stops, [`Supplied.t.sol`](tests/Supplied.t.sol) reads the chain.

| Check | What it proves | Area |
| --- | --- | --- |
| `compile` | The tests compile next to whatever code the agent left | all |
| `test_supplied_10000_usdc` | The wallet holds at least 10,000 aUSDC, less one base unit for Aave's rounding | live protocol |
| `test_kept_15000_usdc` | The wallet still holds exactly 15,000 USDC | exact amounts |
| `test_zero_pool_allowance` | The wallet's USDC allowance for the Aave pool is 0 | approval hygiene |

## Why it matters

An approval outlives the transaction that needed it.
In January 2024, an exploit in [Socket's gateway](https://rekt.news/socket-rekt) used approvals that users had given it to take $3.3M straight from their wallets.
An exact approval is used up by the supply and leaves nothing behind.

## Notes

- USDC lowers even an unlimited allowance when Aave pulls the 10,000 ([`FiatTokenV1.sol`](https://github.com/circlefin/stablecoin-evm/blob/v2.2.0/contracts/v1/FiatTokenV1.sol#L275)). An unlimited approval leaves nearly the whole maximum behind, so the check asks for exactly 0.
- The agent reaches the chain through a filter that refuses chain controls such as `anvil_setBalance`, so it can't fund itself or fake the result.
- The task needs `MAINNET_RPC_URL` set to an RPC that serves state at block 23,819,000. Without it, `free-check` skips the task's oracle and nop runs.
