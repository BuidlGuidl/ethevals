# Swap page

The user asks for a Swap page for ETH, USDC, and USDT on Uniswap.
The verifier drives the page with an injected wallet on a mainnet fork.
It compares the page's amounts and wallet requests with chain balances.

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

The task copies the savings verifier's wallet, isolated fork, static server, and private browser installation:

- Only the chain sidecar receives `MAINNET_RPC_URL`. Build commands run as `agent` without model credentials.
- The verifier stops agent processes before the build and before its fork starts.
- Browser reads reach that fork through Playwright request routing. Other endpoints, WebSockets, and direct chain writes are blocked.
- The wallet signs transactions outside the page and records requests before execution.
- Fork startup, funding, and market fixture failures produce trial errors. Broken pages fail checks with evidence and a screenshot.

The driver uses the page the way a user would:

- It selects tokens through visible controls and checks the resulting pair.
- It types an amount and saves the page text before every action press.
- It finds actions through general action words, button roles, and position near the swap form or inside a dialog.
- It accepts Swap tokens, Get quote, Sign, Permit, Submit, Allow, Enable, Review, Confirm, Approve, Accept, Continue, Refresh, and network Switch controls. Each journey has a six-press limit. Refresh is a fallback. Direction controls and token pickers never count as swap actions.
- If a stale-quote dialog blocks the form, the driver dismisses it before it opens a fresh review.
- It classifies wallet requests by decoded calldata rather than request order.

Every journey starts from the funded snapshot:

- `usdc-eth`, `eth-usdc`, and `usdt-usdc` are the scored successful swaps, of 500 USDC, 1 ETH, and 1,000 USDT. The other three directions are not covered. The USDT journey starts without an allowance.
- `usdt-seeded` replays the USDT swap with a nonzero allowance seeded to the spender the first USDT journey found. It scores the same checks as the successful swaps, including cleared allowances. This models approving 500 exactly, a reverted swap, and a retry with 1,000. On USDT, `approve(1000)` reverts unless the page resets the existing approval to 0 first.
- `drift` swaps 500 USDC to ETH. The wallet hook moves the market about 0.3% just before sending the swap. Only `shows_received` scores this journey, so a receipt that echoes the quote can fail. If the page's slippage makes the swap revert, the journey adds no `shows_received` evidence.
- `moved` swaps 2,000 USDC to ETH. It waits up to 20 seconds for an output amount or an enabled, named Review, Swap, or Confirm button, and opens Review when available. Then it moves the market and observes the page for a fixed minute, independent of any saved page's quote expiry. Of the programmatic checks, only `honors_minimum` scores it. A clean revert with zero user and treasury asset deltas after gas honours the minimum.
- `rejected` swaps 500 USDC to ETH, and the wallet returns error 4001 for the swap request only. Earlier approval or fee transactions go through, so a premature cut remains visible.
- `reverted` swaps 500 USDC to ETH and moves the market inside the wallet hook just before the swap is sent. If the page uses an untouched pool and the swap succeeds, the usual successful fee check applies.

The market moves buy ETH through eight active v3 ETH/stablecoin pools and three main hooked v4 pools.
Each pool's USD-per-ETH price rises about 2%, or 0.3% for `drift`, through actual swaps at the pinned block.
V2 pools stay unmoved, so a page that routes through V2 isn't tested by `drift`, `moved` or `reverted`.
The mover never edits price storage, liquidity, code, or permissions.
For Angstrom pools, it mines an authorized node's empty unlock and the market trade in one block.

| Check | What it proves | Area | Code |
| --- | --- | --- | --- |
| `compile` | "Add a Swap page": build and type check pass | frontend compilation | [test.sh](tests/test.sh) |
| `swaps_assets` | "Swap between those three ... on Uniswap": each scored direction spends the entered amount and receives its output through Uniswap | trading | [browser.mjs](tests/browser.mjs) |
| `cut_only_on_swap` | "A 0.25% cut of each swap": the swap transaction pays 0.25% of input or gross output within 1%; rejected and reverted swaps lose only gas | fee handling | [checks.mjs](tests/checks.mjs) |
| `honors_minimum` | "What they'll get before they confirm": the submitted minimum is at least 99% of the last confirmed minimum, and successful output reaches that display | slippage | [checks.mjs](tests/checks.mjs) |
| `exact_approvals` | "Don't leave open-ended token approvals behind": no token allowance remains to Permit2, listed routers, or observed spenders, and no unexpired Permit2 amount remains | token permissions | [chain.mjs](tests/chain.mjs) |
| `finite_deadline` | "Swap ... on Uniswap": each scored router or Swap-log transaction has a deadline no later than one year after the fork timestamp | transaction lifetime | [decode.mjs](tests/decode.mjs) |
| `native_eth` | "Hold ETH": ETH output arrives as ETH without a WETH balance increase | native currency | [checks.mjs](tests/checks.mjs) |
| `routers_empty` | "Swap between those three": router ETH, WETH, USDC, and USDT balances return to their pinned baseline | settlement | [chain.mjs](tests/chain.mjs) |
| `shows_received` | "What they actually got after": the received amount matches the chain delta within its displayed precision, capped at 1% of the chain amount | receipt display | [checks.mjs](tests/checks.mjs) |
| `explains_price_change` | "What they'll get before they confirm": a notice or refresh step tells the user the quote changed before the wallet request | user feedback, judge | [price-change.toml](tests/price-change.toml) |

The reward is 1 only when every check passes.
RewardKit alone writes the reward from the named check records and the judge.
Free checks skip the paid judge.

The judge checks the page's response to the changed price in `moved`.
Text changes during the move and around every press enter a timestamped timeline, including brief notices.
The judge reads the page before the move, every later press, and the wallet request log.
The runner requires the trajectory input, but the criterion judges page behaviour from the saved timeline and wallet requests.

- It accepts a stale-quote notice with a forced refresh or a new confirmation.
- It judges changes after the user reaches the review or confirmation view. Without a review step, it fails only if the number at press time differs from the request or was stale.
- A live form quote can refresh before review without a notice. Once the user reaches the confirming view, silent replacement of the amounts they must confirm fails.
- An unchanged quote on an untouched route passes without a price-change notice.

The checks read the confirmed minimum this way:

- The parser accepts Minimum received, Min. received, Minimum output, min, at least, or worst-case labels beside the output token. The token can appear before or after the number, including across lines.
- The driver can open one Details, More, or Show disclosure before it reads the minimum.
- Without a minimum, it uses expected output minus stated slippage, with 1% tolerance for both submitted and received amounts. Without both, it records "could not read a minimum".
- The last readable minimum before a user action supplies the confirmed amount. Wallet-pending text cannot erase it or lower it after confirmation.
- Optional Universal Router commands and their nested actions do not contribute to an enforced minimum.
- Router-gross minima can exceed the user's net minimum when the fee comes from output.

The fee, input, and deadline checks work this way:

- The fee check reads treasury balances at the swap's block and the preceding block, for tokens and native ETH. It rejects cuts paid in an earlier or later transaction.
- The fee check treats treasury WETH as ETH at one-to-one value. The user's ETH output must still arrive unwrapped.
- The test wallet is a plain EOA without atomic batching, so a fee that relies on batching fails `cut_only_on_swap`.
- The input debit must match the typed amount within one base unit. An input fee can form part of that amount or be added to it.
- The deadline check rejects bounds more than one year after the fork block's timestamp. It does not require a deadline to follow the current wall clock. Transfers, approvals, and WETH wrapping alone do not trigger it.
- V2 Router02 and SwapRouter02's v2 functions use the same minimum and deadline checks as the other routers.

The instruction asks the page not to leave open-ended token approvals behind.
Uniswap's own app fails this row when it grants a maximum token approval or a reusable maximum Permit2 amount.
A router bug or a phishing signature can spend the remaining wallet balance under those approvals.
An exact one-shot Permit2 signature still fails if the underlying ERC-20 approval to Permit2 remains unlimited.

The approval check reads WETH, USDC, and USDT allowances to these spenders:

- every router in the pinned SDK's mainnet map
- the legacy Universal Router, both v3 routers, and V2 Router02
- approval and Permit2 spenders from each journey's wallet requests, including failed requests
- every swap request's destination

The allowance and router balance checks include those addresses and compare balances with their pinned baseline.

## Why it matters

A fee sent before the swap can leave the user poorer after cancellation or a revert.
Uniswap's [Universal Router commands](https://developers.uniswap.org/docs/protocols/universal-router/concepts/commands) support fee payment inside the swap transaction.
[Permit2 allowance transfer](https://developers.uniswap.org/docs/protocols/permit2/concepts/allowance-transfer) separates token approvals from amount and expiration permissions.
Both layers matter when limiting future spending.

## Notes

- The main container has one CPU and 4 GiB of memory, and the chain sidecar has a 3 GiB limit. The task sets no agent time limit.
- The solution is a reference page with an explicit fresh-price review. Its token picker uses buttons and a dialog to exercise a different control shape. It uses exact approvals and takes the fee from output inside the router transaction.
- The task-local wallet adds transaction classification arguments to its `beforeSend` callback. The task-local RPC helper uses 120-second request and receipt timeouts for fork reads and market transactions. The savings copies do not include these swap-specific changes.
- ETH settlement, empty routers, and receipt amounts partly repeat checks in other page tasks.
- Slippage of 2% or more can let `moved` and `reverted` succeed without testing a stale-price revert.

Run the free check with `MAINNET_RPC_URL` set and all model key variables unset:

```sh
uv run ethevals lint --tasks tasks/building/swap-page
uv run ethevals free-check --tasks tasks/building/swap-page \
  --output /tmp/swap-page-free-check
```

Install `environment/verifier/package.json` into a private local directory for verifier self-tests:

```sh
VERIFIER_DEPS=/path/to/packages \
  node --test tasks/building/swap-page/tests/*.test.mjs
python3 tasks/building/swap-page/tests/test_source_snapshot.py
```

Set `SWAP_FIXTURE_OUTPUT` to replay saved page evidence through the current check functions.
It expects the browser verifier output directories that [fixtures.test.mjs](tests/fixtures.test.mjs) lists.
Those optional self-tests replay receipts and page text through the same `gradeJourney` function as the browser verifier.
They include the failed fee journeys, the USDT to USDC swap, and the entered-amount check.
