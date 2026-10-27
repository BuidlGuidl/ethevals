# Aave savings page

A wallet app wants a Savings page where its users put USDC and USDT into Aave v3, watch the balance grow, and take it back out.
The agent adds that page to a fresh create-wagmi project.

The checks open the built page in a browser with a test wallet and use it the way a person would.
They score what the page asked the wallet for and what changed on chain.

A savings page looks like a few buttons and two numbers, but each part has a detail the request doesn't mention:

- the balance has to include interest;
- the APY has to be compounded;
- Max has to empty the position;
- USDT needs its allowance reset;
- a full supply cap has to stop the page before it asks the wallet for anything.

## The instruction

> Our users hold USDC and USDT on Ethereum mainnet and want to earn on them without leaving our app, so could you add a Savings page to this project? A connected user should be able to deposit either token into Aave v3, see how much they have deposited including interest so far and the current APY, and withdraw part or all of it at any time. The chain to use is in `chain_context.json`.

## What it touches

The instruction names the tokens, the protocol, and what the user can do.
It leaves out the details below, and each one is a check.

### Interest that keeps growing

Aave holds a deposit as aTokens, and the aToken balance grows every second.
A page that shows the amount deposited, or a number it read once, is wrong a block later.
The checks move the clock forward 30 days and reload the page.

```text
100 USDC after 30 days   show 100.325312, not 100
```

### APY, not APR

Aave publishes each reserve's `currentLiquidityRate`, a yearly rate without compounding.
Interest compounds every second, so the rate the user earns is higher.

```text
USDC at block 26260992
currentLiquidityRate as a percent    3.96%   the APR
compounded every second for a year   4.04%   the APY
```

### Withdrawing everything

Interest keeps growing between the moment a page reads the balance and the moment the withdrawal is mined.
A Max button that sends the last balance it read leaves that interest behind.
Aave's pool treats the largest `uint256` as the whole balance, which closes the position exactly.

The checks mine each withdrawal a day after the click.

```text
Max pressed with about 60.34 USDC in Aave, mined a day later
amount sent           USDC back    aUSDC left
last balance read     60.336156    0.006595
type(uint256).max     60.342751    0
```

### USDT's approve

USDT refuses to change an allowance from one non-zero value to another.
If the pool already holds a small USDT allowance, the page has to set it to 0 before approving the new amount.
The checks start the USDT deposit with 1 USDT already approved.

```text
the pool already has a 1 USDT allowance
approve(pool, 100 USDT)                          reverts
approve(pool, 0), then approve(pool, 100 USDT)   works
```

### A full supply cap

Every Aave reserve has a supply cap, and Aave reverts a deposit that would go over it with `SupplyCapExceeded()`.
Aave's own app reads the room left, limits the amount, and asks the wallet for nothing.

A page that asks for an approve first costs the user gas and leaves a live allowance for a deposit that can't happen.
The page should also say why in words, not show the raw error code `0xf58f733a`.

The market the agent builds against has plenty of room.
The checks fill the cap only on their own copy of the chain, so a page passes only if it handles a full cap it never saw.

```text
room left        3,647.67 USDC
the check types  6,000.10 USDC
careful page     asks for nothing, says the cap is full
quick page       sends an approve, then the supply reverts
```

### The wrong network

Users arrive on whatever chain their wallet used last, and the instruction names Ethereum mainnet.
When the user presses Deposit or Withdraw on another chain, the page should switch the wallet to Ethereum and carry on with the action.
It shouldn't send the transaction to the other chain, or stop after the switch and wait for a second click.

## The checks

The verifier builds the project as the agent's user, serves the build with its own static server, and opens it in headless Chromium with an injected test wallet.
It runs its own copy of the task chain and funds a fresh wallet with ETH and 10,000 USDC and USDT.
Then it uses the page the way a person would:

```text
read the APY                      before any action
deposit 100 USDC, wait 30 days    reload, read the balance
withdraw 40 USDC, then Max        each mined a day later
deposit 100 USDT                  1 USDT already approved
fill USDC's cap, try 6,000 USDC   no wallet request allowed
```

How it scores:

- It reads the page's text, the requests the page sent the wallet, and the balances on chain.
- It finds controls by their visible words and the page's structure. A control it can't find fails only the checks that need it, with "could not drive" and a screenshot.
- The reward is 1 only when every check passes.

| Check | What it proves | Area |
| --- | --- | --- |
| `compile` | Both build and type check succeed | frontend compilation |
| `deposit_usdc` | Depositing 100 USDC leaves 100 aUSDC within 0.01 USDC | Aave supply |
| `shows_deposit` | The visible balance matches accrued aUSDC within 0.01 USDC | interest-inclusive balance |
| `shows_apy` | The labelled APY matches per-second compounding within 0.01 percentage points | Aave rates |
| `withdraw_partial` | Withdrawing returns 40 USDC and reduces the accrued position by that amount | Aave withdrawal |
| `withdraw_all` | Max returns the whole position and leaves exactly zero aUSDC | closing a position |
| `deposit_usdt_leftover_allowance` | Depositing 100 USDT succeeds with an existing 1 USDT Pool allowance | token approvals |
| `refuses_over_cap` | When Aave would refuse the deposit, the page asks the wallet for nothing | Aave supply cap |
| `explains_supply_cap` | The page explains the refused deposit's cap in words | user feedback, judge |
| `switches_and_continues` | Deposit or Withdraw switches to Ethereum and carries on without another click | network handling, judge |

Each check rests on words in the instruction and on reference code:

- `compile` rests on "add a Savings page to this project". Reference: the project's build script and `tsc` in [test.sh](tests/test.sh).
- `deposit_usdc` rests on "deposit either token into Aave v3". Reference: Aave [SupplyLogic.executeSupply](https://github.com/aave-dao/aave-v3-origin/blob/8305565ae342f1773c42cd2e4593f175fe5968a0/src/contracts/protocol/libraries/logic/SupplyLogic.sol).
- `shows_deposit` rests on "including interest so far". Reference: Aave [AToken.balanceOf](https://github.com/aave-dao/aave-v3-origin/blob/8305565ae342f1773c42cd2e4593f175fe5968a0/src/contracts/protocol/tokenization/AToken.sol).
- `shows_apy` rests on "the current APY". Reference: Aave [formatReserve](https://github.com/aave/aave-utilities/blob/2d0db501009fdb34824cbc9a486c3e9fd7191ec7/packages/math-utils/src/formatters/reserve/index.ts), compared by [reserve()](tests/chain.mjs).
- `withdraw_partial` rests on "withdraw part ... at any time". Reference: Aave [SupplyLogic.executeWithdraw](https://github.com/aave-dao/aave-v3-origin/blob/8305565ae342f1773c42cd2e4593f175fe5968a0/src/contracts/protocol/libraries/logic/SupplyLogic.sol).
- `withdraw_all` rests on "withdraw ... all of it at any time". Reference: `executeWithdraw`'s [max-uint branch](https://github.com/aave-dao/aave-v3-origin/blob/8305565ae342f1773c42cd2e4593f175fe5968a0/src/contracts/protocol/libraries/logic/SupplyLogic.sol#L124).
- `deposit_usdt_leftover_allowance` rests on "deposit either token". Reference: USDT's verified [approve implementation](https://etherscan.io/address/0xdac17f958d2ee523a2206206994597c13d831ec7#code).
- `refuses_over_cap` rests on "deposit either token into Aave v3". Reference: Aave [SupplyModalContent.tsx](https://github.com/aave/interface/blob/ae94b94ccdc4f370c53c4c78111413ce9790eb1e/src/components/transactions/Supply/SupplyModalContent.tsx#L187-L196), [validateSupply](https://github.com/aave-dao/aave-v3-origin/blob/8305565ae342f1773c42cd2e4593f175fe5968a0/src/contracts/protocol/libraries/logic/ValidationLogic.sol).
- `explains_supply_cap` rests on "deposit either token into Aave v3". Reference: [cap-explanation.toml](tests/cap-explanation.toml) and Aave's supply UI above.
- `switches_and_continues` rests on "Ethereum mainnet" and "The chain to use is in `chain_context.json`". Reference: [network-flow.toml](tests/network-flow.toml).

The cap check is strict:

- Any wallet write counts as asking: a transaction, an approval alone, a signature, or a bundle.
- It waits until the wallet has been idle for three seconds, up to twenty seconds. A request still pending at that point counts.
- A page may simulate the supply before its first wallet prompt, so it needs no explicit cap read.
- A page that cuts the typed amount down to the room and then asks the wallet still fails.
- A control that is disabled, missing, or relabelled after typing counts as no request.
- The same page must first finish a deposit inside the room, so a page that can't deposit at all doesn't pass.
- The room counts the treasury's accrued tokens, as Aave does. Its bounds and the oversized amount live in `capFixture()` in [chain.mjs](tests/chain.mjs).

The two judges run only on the board, not in free checks or PR CI:

- `explains_supply_cap` reads the page's text and screenshot after the refused deposit.
- `switches_and_continues` reads the page's source, without dependencies or build output. It follows Deposit and Withdraw through a network switch to the transaction that follows.

## Why it matters

Aave's own app or the token contract already handles each detail, so a page built on the happy path alone misses it.

- Aave's [supply guide](https://aave.com/help/supplying/supply-tokens) says interest accrues in the supplied balance. Its [formatReserve](https://github.com/aave/aave-utilities/blob/2d0db501009fdb34824cbc9a486c3e9fd7191ec7/packages/math-utils/src/formatters/reserve/index.ts) is how Aave's app turns the liquidity rate into the APY it shows.
- Aave's [withdrawal guide](https://aave.com/help/supplying/withdraw-tokens) covers withdrawals. The pool's [max-uint branch](https://github.com/aave-dao/aave-v3-origin/blob/8305565ae342f1773c42cd2e4593f175fe5968a0/src/contracts/protocol/libraries/logic/SupplyLogic.sol#L124) is what closes a position without dust.
- USDT's [verified contract](https://etherscan.io/address/0xdac17f958d2ee523a2206206994597c13d831ec7#code) rejects a non-zero approve over a non-zero allowance. USDT is one of the two tokens the user asked for, so skipping the reset breaks the deposit for anyone with a leftover allowance.
- Aave's [Supply modal](https://github.com/aave/interface/blob/ae94b94ccdc4f370c53c4c78111413ce9790eb1e/src/components/transactions/Supply/SupplyModalContent.tsx#L187-L196) checks the cap's room before any wallet prompt, as the contract's [validateSupply](https://github.com/aave-dao/aave-v3-origin/blob/8305565ae342f1773c42cd2e4593f175fe5968a0/src/contracts/protocol/libraries/logic/ValidationLogic.sol) does.
- [EIP-3326](https://eips.ethereum.org/EIPS/eip-3326) defines `wallet_switchEthereumChain`, the request a page sends to move the wallet to the right network.

## Notes

Two practices are deliberately not checked:

- **Exact approvals.** Aave's own app approves the largest `uint256` when it supplies without a permit, through `useApprovalTx` in `SupplyActions.tsx` and `poolSlice.ts`.
- **One-transaction deposits.** The instruction sets no rule on wallet prompts, and the reference apps disagree. Aave's app uses a permit, while MetaMask Mobile's lending batched approve and supply and then turned batching off.

The controls are found by words and page structure, tested on ten pages built by agents and ten fixture pages.
A page laid out in a way they don't cover fails with "could not drive" and a screenshot, so a person should look at such a fail before it is published.

`solution/solve.sh` copies a working Savings page into the project.
When the wallet supports atomic batching, it sends approve and supply as one bundle.
The untouched starter compiles but has no Savings controls, so its browser checks fail.

### The project and the chain

The project:

- The agent starts in `/workspace` with the create-wagmi 2.0.19 vite-react project.
- Its lockfile pins wagmi 3.7.9, viem 2.57.11, React 19.3.1, and Vite 8.3.5. The image installs them during the build, so a trial needs no npm download.
- The main image adds Node.js 22 and pnpm 9.14.2 to the shared chain image, plus curl, bash, procps, and ripgrep for Harbor's agent installers. Harbor can still download the selected agent CLI during setup.
- The main container gets one CPU and 4 GiB of memory, and the chain sidecar gets 3 GiB. The task adds no agent time limit.

The chain:

- It forks Ethereum mainnet at block `26260992`, from 2026-10-24 at 07:25:11 UTC, which was finalized when checked.
- At that block, Aave v3's main pool, `0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2`, has active, unfrozen, unpaused USDC and USDT reserves.
- USDC's cap there is 3,000,000,000 USDC with about 609.6M of room.
- Setup changes nothing on the chain and funds no wallet. It writes the chain context, which the agent reads at `/workspace/chain_context.json`.
- Only the chain sidecar receives `MAINNET_RPC_URL`.

### How the verifier runs

The browser stays out of the agent's reach:

- Playwright 1.61.1, Chromium, and viem 2.57.11 live in root-only directories.
- The image extracts Chromium's extra shared libraries under `/root/savings-libs` instead of installing them system-wide. Only the verifier's browser launch gets that path.
- A Chromium the agent downloads can't launch with the system libraries alone.

The order of a run:

1. `test.sh` kills leftover agent processes.
2. It runs `pnpm build` and `tsc --noEmit` as `agent`, with verifier credentials removed.
3. It kills agent processes again, so none runs beside the verifier's fork.
4. It starts its own Anvil fork of the task chain. The fork is unfiltered so the verifier can fund wallets, take snapshots, and move the clock.
5. It runs the journeys in `browser.mjs`, then RewardKit.

The page and the wallet:

- Playwright injects an EIP-1193 provider and announces it through EIP-6963.
- The wallet's private key stays in the verifier process and never reaches the page or the public chain context.
- Browser JSON-RPC reads, including `/rpc` paths and Docker hostnames, reach the verifier's fork through request routing.
- The page and the wallet share a read allowlist that mirrors the task chain's, without raw transaction submission. Other endpoints and WebSockets are blocked.
- The static server serves `dist/` without loading the Vite config or package scripts. The verifier never changes the agent's source.

Time, snapshots, and the cap:

- The fork's block interval is zero, and the verifier moves time only where a journey needs it.
- Snapshots isolate the USDT and cap journeys. Each withdrawal journey gets a funded position if the one before it failed.
- For the cap journey alone, the verifier impersonates the provider's ACL admin, after checking its pool admin role, and lowers USDC's cap through the pool configurator.
- The new cap is the aUSDC total supply rounded up to whole USDC, plus 5,000 USDC. Accrued treasury tokens leave less than that as room.
- The admin holds no ETH, so that block's base fee and gas price are zero. The clock stays still during the journey.
- Pool revision 11 reverts with `SupplyCapExceeded()`, selector `0xf58f733a`, where older pools used the string error `51`.

Outputs:

- Each journey saves page text, a screenshot, and the wallet requests with their receipts.
- The verifier writes `build.log`, `typecheck.log`, and `checks.json` under `/logs/verifier/`.
- It copies `/opt/check_records.py` into `/tests/check_records.py`, and RewardKit uses that shared adapter to turn `checks.json` into named checks and the reward.
- Fork startup, funding, and fixture failures are trial errors. Broken pages and builds fail their checks.
- Harbor saves `/workspace` as an artifact, without `node_modules`, `dist`, `.git`, and `chain_context.json`. Leaving out the chain context symlink lets the publication secret check scan the saved project, since it rejects symlinks.

The wallet also supports atomic bundles and ERC-1271 signatures through an EIP-7702 account, for later page tasks.
Savings runs no atomic journey.

### Running the checks

With `MAINNET_RPC_URL` set, run the free check from the repository root:

```sh
uv run ethevals lint \
  --tasks tasks/build/aave-savings-page
uv run ethevals free-check \
  --tasks tasks/build/aave-savings-page \
  --output /tmp/aave-savings-free-check
```

To run either free agent directly through Harbor:

```sh
uv run harbor run -p tasks/build/aave-savings-page \
  -a oracle -e docker --n-concurrent 1
uv run harbor run -p tasks/build/aave-savings-page \
  -a nop -e docker --n-concurrent 1
```

Verifier self-tests run outside scored trials.
Install the pinned verifier packages in a directory you own, then run these commands from the repository root:

```sh
T=tasks/build/aave-savings-page/tests
VERIFIER_DEPS=/path/to/verifier-packages \
  node --test $T/*.test.mjs
python3 $T/test_source_snapshot.py
```

- The Node tests need Anvil and a Playwright Chromium installation.
- The package versions are in `environment/verifier/package.json`.
- Set `PLAYWRIGHT_BROWSERS_PATH` if your browser installation uses a custom directory.

To look at a saved project, open the trial's `artifacts/workspace/` directory and install dependencies from its lockfile.
For live chain access, add a `chain_context.json` file for your own fork.

### Copying the verifier to another page task

Each task owns its verifier files, and no task imports another task at runtime.

Copy these into the new task's `tests/`:

- `deps.mjs`, `rpc.mjs`, `rpc-policy.mjs`, `wallet.mjs`, `harness.mjs`, `static-server.mjs`, and `control-vocabulary.mjs`
- `stop-agent.py`, and the unprivileged build steps from `test.sh`
- `Wallet.sol` and `wallet-bytecode.txt`, if the task tests atomic bundles

What the copied files give you:

- `createHarness({workspace, output, sourceContext, funding})` creates the fork, funded account, browser, and static server.
- `funding` supplies `nativeBalance` and token transfers, each with `token`, `holder`, and `amount`.
- The returned object exposes `mainRpc`, `account`, `sourceBlock`, `session`, `reset`, `capture`, and `close`.
- `session({atomic, beforeSend})` opens the built page and returns `page`, `context`, `wallet`, and `errors`.
- `reset()` closes that session and restores the funded snapshot.
- `close()` stops the browser, server, and fork.
- The wallet records requests before execution and transactions after mining.
- `createVocabulary(words, {prerequisites})` supplies matching and submission helpers for the new task's action words.

What the new task supplies:

- Its journeys, chain setup, funding addresses, expected values, and page-specific control scopes. For Savings, those live in `browser.mjs`, `chain.mjs`, and `controls.mjs`.
- Its own check names, and which failures are trial errors.
- The check-record and RewardKit wiring, adapted from `test.sh`.

Keep state that only a check needs, like the full cap here, in the verifier's fork, so the agent builds against the real chain.

For the image:

- Copy `environment/verifier/`, including the lockfile and private font configuration.
- In the Dockerfile, copy Node and install pnpm, then copy this task's root-only verifier installation block. It downloads library packages, extracts them under `/root/savings-libs`, and installs Chromium without `--with-deps`.
- Keep the `COPY verifier/fonts.conf /root/savings-fonts.conf` line and the `chmod 700` paths, consistent with `deps.mjs`, `harness.mjs`, and `test.sh`.
- No shared-image change is needed.
