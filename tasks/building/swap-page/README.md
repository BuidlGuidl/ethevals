# Swap page

The user asks for a Swap page for ETH, USDC, and USDT on Uniswap.
The verifier drives the page with an injected wallet on a mainnet fork.
It compares the page's amounts and wallet requests with chain balances.

## The instruction

```text
Our users hold ETH, USDC and USDT on Ethereum mainnet and keep leaving our app to trade. Add a Swap page to this project where a connected user can swap between those three on Uniswap. Show them what they'll get before they confirm, and what they actually got after. We take a 0.25% cut of each swap, paid to our treasury address in `chain_context.json`. The chain to use is in `chain_context.json` too.
```

## What it touches

The environment uses the create-wagmi 2.0.19 Vite React project from the Aave savings task.
The chain forks Ethereum mainnet at block `26260992`.
Setup records a fresh treasury address without code in the trusted chain context at `/chain/chain_context.json`.
No Uniswap version or quote API appears in the instruction or starting project.
The agent has no quote API key.

The task copies the savings verifier's wallet, isolated fork, static server, and private browser installation.
Only the chain sidecar receives `MAINNET_RPC_URL`.
Build commands run as `agent` without model credentials.
The verifier stops agent processes before the build and before its fork starts.
Browser reads reach that fork through Playwright request routing.
Other endpoints, WebSockets, and direct chain writes are blocked.
The wallet signs transactions outside the page and records requests before execution.
Fork startup, funding, and market fixture failures produce trial errors.
Broken pages fail checks with evidence and a screenshot.

## The checks

The driver selects tokens through visible controls and checks the resulting pair.
It types an amount and saves the page text before every action press.
It presses through Swap, Review, Confirm, Approve, Accept, Continue, Refresh, and network Switch controls, with a six-press limit.
Refresh is a fallback when no swap or confirmation action is enabled.
If an expired review says to close it to refresh, the driver follows that instruction before it opens a fresh review.
Direction controls never count as swap actions.
It classifies wallet requests by decoded calldata rather than request order.
Every journey starts from the funded snapshot.
Scored successful journeys cover USDC to ETH, ETH to USDC, and USDT to USDC.
They do not cover the other three directions.
The USDT journey starts without an allowance.
A replay seeds a nonzero allowance to its discovered spender, but that replay supplies evidence only.
Failure to reset USDT approval does not affect the reward.

| Check | What it proves | Area | Instruction words | Reference code |
| --- | --- | --- | --- | --- |
| `compile` | Build and type check pass | frontend compilation | "Add a Swap page" | [test.sh](tests/test.sh) |
| `swaps_assets` | Each scored direction spends the entered amount and receives its output through Uniswap | trading | "swap between those three ... on Uniswap" | [browser.mjs](tests/browser.mjs) |
| `cut_only_on_swap` | The swap transaction pays 0.25% of input or gross output within 1%; rejected and reverted swaps lose only gas | fee handling | "a 0.25% cut of each swap" | [checks.mjs](tests/checks.mjs) |
| `honors_minimum` | The submitted minimum is at least 99% of the last confirmed minimum; successful output reaches that display | slippage | "what they'll get before they confirm" | [checks.mjs](tests/checks.mjs) |
| `exact_approvals` | No token allowance remains to Permit2, listed routers, or observed spenders; no unexpired Permit2 amount remains | token permissions | Maintainer requirement described below | [chain.mjs](tests/chain.mjs) |
| `finite_deadline` | Each scored router or Swap-log transaction has a deadline no later than one year after the fork timestamp | transaction lifetime | "swap ... on Uniswap" | [decode.mjs](tests/decode.mjs) |
| `native_eth` | ETH output arrives as ETH without a WETH balance increase | native currency | "hold ETH" | [checks.mjs](tests/checks.mjs) |
| `routers_empty` | Router ETH, WETH, USDC, and USDT balances return to their pinned baseline | settlement | "swap between those three" | [chain.mjs](tests/chain.mjs) |
| `shows_received` | The received amount matches the chain delta within its displayed precision | receipt display | "what they actually got after" | [checks.mjs](tests/checks.mjs) |
| `explains_price_change` | A notice or refresh step tells the user the quote changed before the wallet request | user feedback, judge | "what they'll get before they confirm" | [price-change.toml](tests/price-change.toml) |

The reward is 1 only when every check passes.
RewardKit alone writes the reward from the named check records and the judge.
Free checks skip the paid judge.
The judge reads the page before the move, every subsequent press, and the wallet request log.
The runner requires the trajectory input; the criterion judges page behaviour from the saved timeline and wallet requests.
It accepts a stale-quote notice with a forced refresh or a new confirmation.
Judge changes after the user reaches the review or confirmation view.
If there is no review step, judge the view with the Swap button.
A live form quote can refresh before review without a notice.
Once the user reaches the confirming view, silent replacement of the amounts they must confirm fails.
An unchanged quote on an untouched route passes without a price-change notice.

The market journeys buy ETH through eight active v3 ETH/stablecoin pools and three main hooked v4 pools.
Each pool's USD-per-ETH price rises about 2% through actual swaps.
The mover never edits price storage, liquidity, code, or permissions.
It uses the kit's measured pool inventory at the pinned block.
For Angstrom pools, it mines an authorized node's empty unlock and the market trade in one block.
One journey waits up to 20 seconds for an output amount or an enabled, named Review, Swap, or Confirm button.
It opens Review when available before it moves the market.
It then observes the page for a fixed minute, independent of any saved page's quote expiry.
Text changes during the move and around every press enter a timestamped timeline, including brief notices.
Only `honors_minimum` scores this journey.
A clean revert with zero user and treasury asset deltas after gas honours the minimum.
The judge checks the page's response to the changed price.
Another moves it inside the wallet hook immediately before sending the swap.
If the page uses an untouched pool and the latter swap succeeds, the usual successful fee check applies.
The cancellation journey returns wallet error 4001 only for the swap request.
It permits earlier approval or fee transactions so a premature cut remains visible.

The minimum parser accepts minimum, min, at least, or worst-case labels beside the output token.
The driver can open one Details, More, or Show disclosure before it reads the minimum.
The token can appear before or after the number, including across lines.
Without a minimum, it uses expected output minus stated slippage, with 1% tolerance for both submitted and received amounts.
Without both, it records "could not read a minimum".
The last readable minimum before a user action supplies the confirmed amount.
Wallet-pending text cannot erase it or lower it after confirmation.
Optional Universal Router commands and their nested actions do not contribute to an enforced minimum.
Router-gross minima can exceed the user's net minimum when the fee comes from output.
The fee check treats treasury WETH as ETH at one-to-one value; the user's ETH output must still arrive unwrapped.
The deadline check rejects bounds more than one year after the fork block's timestamp.
It does not require a deadline to follow the current wall clock.
Transfers, approvals, and WETH wrapping alone do not trigger it.
V2 Router02 and SwapRouter02's v2 functions use the same minimum and deadline checks as the other routers.
The fee check reads treasury balances at the swap's block and the preceding block, for tokens and native ETH.
It rejects cuts paid in an earlier or later transaction.
The test wallet is a plain EOA without atomic batching, so a fee that relies on batching fails `cut_only_on_swap`.
The input debit must match the typed amount within one base unit.
An input fee can form part of that amount or be added to it.

Exact approval is the maintainers' choice and goes beyond the instruction's explicit words.
Uniswap's own app fails this row when it grants a maximum token approval or a reusable maximum Permit2 amount.
A router bug or a phishing signature can spend the remaining wallet balance under those approvals.
An exact one-shot Permit2 signature still fails if the underlying ERC-20 approval to Permit2 remains unlimited.
The check reads WETH, USDC, and USDT allowances to every router in the pinned SDK's mainnet map.
It also includes the legacy Universal Router, both v3 routers, and V2 Router02.
Each journey adds approval and Permit2 spenders from wallet requests, including failed requests, and every swap request's destination.
The allowance and router balance checks include those addresses and compare balances with their pinned baseline.

## Why it matters

A fee sent before the swap can leave the user poorer after cancellation or a revert.
Uniswap's [Universal Router commands](https://docs.uniswap.org/contracts/universal-router/technical-reference) support fee payment inside the swap transaction.
[Permit2 allowance transfer](https://docs.uniswap.org/contracts/permit2/reference/allowance-transfer) separates token approvals from amount and expiration permissions.
Both layers matter when limiting future spending.

ETH settlement, empty routers, and receipt amounts partly repeat checks in other page tasks.

## Notes

The main container has one CPU and 4 GiB of memory; the chain sidecar has a 3 GiB limit.
The task sets no agent time limit.
The solution adapts the saved Opus page and adds an explicit fresh-price review.
Its token picker uses buttons and a dialog to exercise a different control shape.
It uses exact approvals and takes the fee from output inside the router transaction.
The task-local wallet adds transaction classification arguments to its `beforeSend` callback.
The task-local RPC helper uses 120-second request and receipt timeouts for fork reads and market transactions.
The savings copies do not include these swap-specific changes.

Run the free check with `MAINNET_RPC_URL` set and all model key variables unset:

```sh
uv run ethevals lint --tasks tasks/building/swap-page
uv run ethevals free-check --tasks tasks/building/swap-page --output /tmp/swap-page-free-check
```

Install `environment/verifier/package.json` into a private local directory for verifier self-tests:

```sh
VERIFIER_DEPS=/path/to/packages node --test tasks/building/swap-page/tests/*.test.mjs
python3 tasks/building/swap-page/tests/test_source_snapshot.py
```

Set `SWAP_FIXTURE_OUTPUT` to replay saved page evidence through the current check functions.
It expects `opus-final`, `kimi-final`, and `solution-picker` directories from the browser verifier.
Those optional self-tests replay receipts and page text through the same `gradeJourney` function as the browser verifier.
They include the failed fee journeys, the USDT to USDC swap, and the entered-amount check.
