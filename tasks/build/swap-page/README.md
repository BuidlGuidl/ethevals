# Swap page

The user asks for a Swap page for ETH, USDC, and USDT on Uniswap.
An agent judge uses the built page with a funded wallet on a private mainnet copy.
Code checks read the wallet log and chain after the judge finishes.

## The instruction

> Our users hold ETH, USDC and USDT on Ethereum mainnet and keep leaving our app to trade. Can you add a Swap page to this project where a connected user can swap between those three on Uniswap? Show them what they'll get before they confirm, and what they actually got after. Don't leave open-ended token approvals behind. We take a 0.25% cut of each swap, paid to our treasury. Its address and the chain to use are in `chain_context.json`.

## What it touches

- **When the cut is paid.** The 0.25% cut has to travel inside the swap transaction. A cut sent before the swap leaves the user poorer when they cancel or the swap reverts.
- **The amount the user confirmed.** The swap must enforce the minimum the page showed at confirmation. If the price moves while the user reviews the quote, the page has to say so before the wallet request.
- **Token permissions.** After a swap, no standing permission remains at the ERC-20 or the Permit2 layer. An exact Permit2 permit alone does not clear the underlying token approval.
- **Settlement.** Each swap carries a deadline, ETH arrives as ETH rather than WETH, and the routers keep nothing.
- **What the user got.** The page shows the amount the chain delivered.

## The checks

The agent starts from the create-wagmi 2.0.19 Vite React project from the Aave savings task.
The chain forks Ethereum mainnet at block `26260992`.
Setup records a fresh treasury address without code in the trusted chain context at `/chain/chain_context.json`.
Neither the instruction nor the starting project names a Uniswap version or a quote API, and the agent has no quote API key.

The verifier stops submitted processes, builds as the agent user without model credentials, and starts its private chain copy.
It funds a wallet with 10 ETH, 10,000 USDC, and 10,000 USDT.
Pool warm-up and the static server stay verifier-owned.
Playwright routes page reads to that copy and blocks direct writes and outside endpoints.
The wallet signs outside the page and records every request and transaction.

RewardKit runs Claude Code on Opus 5.5 at high effort, paid by the Claude plan.
The judge starts at `/judge`, one folder above the submitted source in `/judge/submission`.
It gets the built page through Playwright, chain reads through `cast`, and fixture commands.
User-level settings permit read-only chain commands and disable background tasks.
The browser allow list excludes code execution in the MCP process.

Before each swap, `wallet-test <input> <output> <amount> [mode]` records the intended amount for the chain checks.
The judge chooses the page's controls itself.
It covers 1 ETH to USDC, 500 USDC to ETH, and 1,000 USDT to USDC.
It repeats the USDT swap with a leftover 1 USDT allowance to the spender found in its first USDT swap.
`reject` refuses the swap request after earlier approval or fee requests have run.
`race` moves the market 2% inside the wallet just before sending the swap.
`moved` allows the page to cancel a stale quote without sending a transaction.
The judge also tests a 0.3% price move and a 2% move before the wallet request.

`move-price <percent>` buys ETH through eight active v3 pools and three hooked v4 pools.
It changes prices through real swaps without editing pool storage, liquidity, code, or permissions.
V2 pools stay unchanged.
For Angstrom pools, the mover mines an authorized node's unlock and its trade in one block.

| Check | What it proves | Area | Code |
| --- | --- | --- | --- |
| `compile` | The build and type check pass | frontend compilation | [test.sh](tests/test.sh) |
| `swaps_assets` | The required directions and seeded USDT swap succeed through Uniswap, and successful swaps spend the entered amount | trading | [session.mjs](tests/session.mjs) |
| `cut_only_on_swap` | Each successful swap transaction pays 0.25% of input or gross output within 1%; cancellation and reverts lose only gas | fee handling | [checks.mjs](tests/checks.mjs) |
| `exact_approvals` | Successful swaps leave no ERC-20 allowance or unexpired Permit2 amount to listed routers, Permit2, or observed spenders | token permissions | [chain.mjs](tests/chain.mjs) |
| `finite_deadline` | Each router or Swap-log transaction has a decoded deadline no later than one year after the fork timestamp | transaction lifetime | [decode.mjs](tests/decode.mjs) |
| `native_eth` | Successful ETH output arrives as ETH without a WETH balance increase | native currency | [checks.mjs](tests/checks.mjs) |
| `routers_empty` | Router ETH, WETH, USDC, and USDT balances return to their initial values | settlement | [chain.mjs](tests/chain.mjs) |
| `shows_received` | After a swap, the page shows what the user actually received | receipt display, judge | [page.toml](tests/page.toml) |
| `honors_minimum` | The page shows a minimum and each swap keeps to it | slippage, judge | [page.toml](tests/page.toml) |
| `explains_price_change` | When a price move prevents the shown minimum, the page tells the user before asking the wallet | user feedback, judge | [page.toml](tests/page.toml) |

The wallet session saves chain snapshots at swap boundaries.
The code checks decide each swap group from those snapshots and receipts after the judge finishes.
Treasury deltas at each successful swap's block must match the group's total treasury deltas.
That rejects cuts paid before or after the swap transaction.
Treasury WETH counts as ETH for the fee, but the user's ETH output must arrive unwrapped.
The wallet is an EOA without atomic batching.
The input cut can form part of the entered amount or be added to it.
The allowance and router checks include listed SDK routers, legacy routers, and spenders from wallet requests.

RewardKit writes one reward after the judge and code checks finish.
Every check must pass for reward 1.
A judge crash or timeout leaves no reward and produces a trial error.
A page the judge cannot use receives no on its criteria.
The free check removes the judge and uses a walk-through guarded by the exact solution source hash.
That walk-through never runs on different submitted source.

## Why it matters

A fee sent before the swap can leave the user poorer after cancellation or a revert.
Uniswap's [Universal Router commands](https://developers.uniswap.org/docs/protocols/universal-router/concepts/commands) support fee payment inside the swap transaction.
[Permit2 allowance transfer](https://developers.uniswap.org/docs/protocols/permit2/concepts/allowance-transfer) separates token approvals from amount and expiration permissions.
Both layers matter when limiting future spending.

## Notes

The main container has one CPU and 4 GiB of memory, and the chain has a 3 GiB limit.
The task sets no agent time limit.
Past-block chain reads run one at a time because concurrent fork reads can block Anvil on one CPU.
A route through an unmoved V2 pool does not exercise a stale-price failure.

Run the free check with `MAINNET_RPC_URL` set and model credentials unset:

```sh
uv run ethevals lint --tasks tasks/build/swap-page
uv run ethevals free-check --tasks tasks/build/swap-page --output /tmp/swap-page-free-check
```

Run verifier behavior tests with the task's verifier packages installed in a private directory:

```sh
VERIFIER_DEPS=/path/to/packages node --test tasks/build/swap-page/tests/*.test.mjs
```
