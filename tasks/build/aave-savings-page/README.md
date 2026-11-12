# Aave savings page

A wallet app wants a Savings page where its users put USDC and USDT into Aave v3, watch the balance grow, and take it back out.
The agent adds that page to a fresh create-wagmi project.

A judge opens the built page in a browser with a test wallet and uses it the way a person would.
Code then reads what the page asked the wallet for and what changed on chain.

A savings page looks like a few buttons and two numbers, but each part has a detail the request doesn't mention:

- the balance has to include interest;
- the APY has to be compounded;
- Max has to empty the position;
- USDT needs its allowance reset;
- a deposit above Aave's supply-cap room must stop before the page asks the wallet to approve or supply it.

## The instruction

> Our users hold USDC and USDT on Ethereum mainnet and want to earn on them without leaving our app, so could you add a Savings page to this project? A connected user should be able to deposit either token into Aave v3, see how much they have deposited including interest so far and the current APY, and withdraw part or all of it at any time. The chain to use is in `chain_context.json`.

## What it touches

The instruction names the tokens, the protocol, and what the user can do.
It leaves out the details below, and each one is a check.

### Interest that keeps growing

Aave holds a deposit as aTokens, and the aToken balance grows every second.
A page that shows the amount deposited, or a number it read once, is wrong a block later.
The judge moves the clock forward 30 days and looks at the page again.

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

The test wallet mines each withdrawal a day after the page asks for it.

```text
Max pressed with about 60.34 USDC in Aave, mined a day later
amount sent           USDC back    aUSDC left
last balance read     60.336156    0.006595
type(uint256).max     60.342751    0
```

### USDT's approve

USDT refuses to change an allowance from one non-zero value to another.
If the pool already holds a small USDT allowance, the page has to set it to 0 before approving the new amount.
The judge starts the USDT deposit with 1 USDT already approved.

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
The verifier fills the cap only on its own copy of the chain, so a page passes only if it handles a full cap it never saw.

```text
room left        about 5,000 USDC
the judge enters 6,000.10 USDC
careful page     asks for nothing, says the cap is full
quick page       sends an approve, then the supply reverts
```

### The wrong network

Users arrive on whatever chain their wallet used last, and the instruction names Ethereum mainnet.
When the user presses Deposit or Withdraw on another chain, the page should switch the wallet to Ethereum and carry on with the action.
It shouldn't send the transaction to the other chain, or stop after the switch and wait for a second click.

## The checks

The verifier builds the project as the agent's user and serves the build with its own static server.
It runs its own copy of the task chain and funds a fresh wallet with 10 ETH, 10,000 USDC and 10,000 USDT.

A judge then uses the page.
RewardKit runs Claude Code on Opus 5.5 at high effort, paid by the Claude plan.
The judge starts at `/judge`, one folder above the submitted source in `/judge/submission`.
It gets the built page through Playwright, chain reads through `cast`, and four commands:

```text
move-time <days>              moves the chain's clock forward
old-usdt-approval             leaves a 1 USDT approval from the wallet to the Pool
full-cap                      lowers USDC's supply cap to leave about 5,000 USDC of room
wallet-network <chain id>     puts the wallet on another network
```

Its prompt asks it to cover at least these:

```text
deposit 100 USDC
look at the page again after move-time 30
withdraw 40 USDC, then everything        each mined a day later
deposit 100 USDT                         after old-usdt-approval
a USDC deposit above the room            after full-cap
press Deposit on another network         after wallet-network
```

The judge chooses the page's controls itself and answers four criteria.
After it finishes, code reads the wallet's log and the chain for the other checks.
The reward is 1 only when every check passes.

| Check | What it proves | Area | Code |
| --- | --- | --- | --- |
| `compile` | Both build and type check succeed | frontend compilation | [test.sh](tests/test.sh) |
| `deposit_usdc` | A page transaction adds 100 aUSDC within 0.01 USDC | Aave supply | [checks.mjs](tests/checks.mjs) |
| `withdraw_partial` | A page transaction returns exactly 40 USDC and removes 40 aUSDC within 0.01 USDC | Aave withdrawal | [checks.mjs](tests/checks.mjs) |
| `withdraw_all` | A page withdrawal, mined a day later, returns a position of at least 1 USDC whole and leaves exactly zero aUSDC | closing a position | [checks.mjs](tests/checks.mjs) |
| `deposit_usdt_leftover_allowance` | After the 1 USDT Pool approval, a page transaction adds 100 aUSDT within 0.01 USDT | token approvals | [checks.mjs](tests/checks.mjs) |
| `refuses_over_cap` | After `full-cap`, the wallet receives no USDC supply or Pool approval above the recorded room | Aave supply cap | [checks.mjs](tests/checks.mjs) |
| `shows_deposit` | After a deposit, the page shows how much the user has deposited, including interest | interest-inclusive balance, judge | [page.toml](tests/page.toml) |
| `shows_apy` | The page shows the current APY, matching Aave's rate on the chain | Aave rates, judge | [page.toml](tests/page.toml) |
| `explains_supply_cap` | When a deposit is more than Aave will accept, the page says Aave's limit is the reason | user feedback, judge | [page.toml](tests/page.toml) |
| `switches_and_continues` | Deposit or Withdraw switches to Ethereum and carries on without another click | network handling, judge | [page.toml](tests/page.toml) |

Each check rests on words in the instruction and on reference code:

- `compile` rests on "add a Savings page to this project". Reference: the project's build script and `tsc` in [test.sh](tests/test.sh).
- `deposit_usdc` rests on "deposit either token into Aave v3". Reference: Aave [SupplyLogic.executeSupply](https://github.com/aave-dao/aave-v3-origin/blob/8305565ae342f1773c42cd2e4593f175fe5968a0/src/contracts/protocol/libraries/logic/SupplyLogic.sol).
- `shows_deposit` rests on "including interest so far". Reference: Aave [AToken.balanceOf](https://github.com/aave-dao/aave-v3-origin/blob/8305565ae342f1773c42cd2e4593f175fe5968a0/src/contracts/protocol/tokenization/AToken.sol).
- `shows_apy` rests on "the current APY". Reference: Aave [formatReserve](https://github.com/aave/aave-utilities/blob/2d0db501009fdb34824cbc9a486c3e9fd7191ec7/packages/math-utils/src/formatters/reserve/index.ts).
- `withdraw_partial` rests on "withdraw part ... at any time". Reference: Aave [SupplyLogic.executeWithdraw](https://github.com/aave-dao/aave-v3-origin/blob/8305565ae342f1773c42cd2e4593f175fe5968a0/src/contracts/protocol/libraries/logic/SupplyLogic.sol).
- `withdraw_all` rests on "withdraw ... all of it at any time". Reference: `executeWithdraw`'s [max-uint branch](https://github.com/aave-dao/aave-v3-origin/blob/8305565ae342f1773c42cd2e4593f175fe5968a0/src/contracts/protocol/libraries/logic/SupplyLogic.sol#L124).
- `deposit_usdt_leftover_allowance` rests on "deposit either token". Reference: USDT's verified [approve implementation](https://etherscan.io/address/0xdac17f958d2ee523a2206206994597c13d831ec7#code).
- `refuses_over_cap` rests on "deposit either token into Aave v3". Reference: Aave [SupplyModalContent.tsx](https://github.com/aave/interface/blob/ae94b94ccdc4f370c53c4c78111413ce9790eb1e/src/components/transactions/Supply/SupplyModalContent.tsx#L187-L196), [validateSupply](https://github.com/aave-dao/aave-v3-origin/blob/8305565ae342f1773c42cd2e4593f175fe5968a0/src/contracts/protocol/libraries/logic/ValidationLogic.sol).
- `explains_supply_cap` rests on "deposit either token into Aave v3". Reference: Aave's supply UI above.
- `switches_and_continues` rests on "Ethereum mainnet" and "The chain to use is in `chain_context.json`". Reference: [EIP-3326](https://eips.ethereum.org/EIPS/eip-3326).

The chain checks read every page transaction the wallet mined, with the wallet's balances just before and after it.
The judge may make extra deposits and withdrawals; each check needs one transaction that meets it.

The cap check uses the verifier's condition records and wallet log:

- The verifier must run `full-cap` and record the room that Aave reports on the chain.
- Each later USDC supply request or USDC approval to the Pool must fit within the latest recorded room.
- Transactions and bundles count even when the wallet refuses them or the chain reverts them.
- Withdrawals and requests within the room do not count against this check.
- The check uses no typing events or page-reported attempt boundaries.
- The page judge checks the cap explanation while entering an amount above the room.
- The same page must also pass `deposit_usdc`, so a page that can't deposit at all doesn't pass.
- The room counts the treasury's accrued tokens, as Aave does. `lowerSupplyCap()` in [chain.mjs](tests/chain.mjs) sets and checks it.

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
4. `run_reward.py` installs the pinned Claude Code 2.1.321 and Playwright MCP 0.0.85, which drives the image's existing Chromium.
5. `session.mjs` starts its own Anvil fork of the task chain, the static server, and the wallet. The fork is unfiltered so the verifier can fund wallets and move the clock.
6. The judge uses the page and answers its criteria.
7. The session reads the chain for the code checks, and RewardKit writes one reward.

If the project does not compile, no session or judge runs, and every check fails.
A judge crash or timeout leaves no reward and produces a trial error.
A page the judge cannot use receives no on its criteria.

The page and the wallet:

- Playwright MCP's page setup injects an EIP-1193 provider and announces it through EIP-6963.
- The wallet starts on Ethereum. After `wallet-network`, it reports the other chain, switches back when the page asks, and sends nothing while away.
- The wallet's private key stays in the verifier process and never reaches the page or the public chain context.
- Browser JSON-RPC reads, including `/rpc` paths and Docker hostnames, reach the verifier's fork through request routing.
- The page and the wallet share a read allowlist that mirrors the task chain's, without raw transaction submission. Other endpoints and WebSockets are blocked.
- The static server serves `dist/` without loading the Vite config or package scripts. The verifier never changes the agent's source.

Time, snapshots, and the cap:

- The fork's block interval is zero. Time moves only on `move-time` and a day before each withdrawal is mined.
- Before the judge starts, `warm.mjs` reads the reserve and token state the pages read. It also simulates the deposits and withdrawals with `eth_simulateV1`, which changes nothing.
- On `full-cap`, the verifier impersonates the provider's ACL admin, after checking its pool admin role, and lowers USDC's cap through the pool configurator.
- The new cap is what Aave counts as supplied, including the treasury's accrued tokens, rounded up to whole USDC, plus 5,000 USDC.
- The admin holds no ETH, so that block's base fee and gas price are zero.
- Pool revision 11 reverts with `SupplyCapExceeded()`, selector `0xf58f733a`, where older pools used the string error `51`.

Outputs:

- The verifier writes `build.log`, `typecheck.log`, and `checks.json` under `/logs/verifier/`.
- The session saves the wallet's log, condition commands, and each page transaction's balances.
  It also saves the judge's trajectory, answers, browser files, and chain context.
- It copies `/opt/check_records.py` into `/tests/check_records.py`, and RewardKit uses that shared adapter to turn `checks.json` into named checks and the reward.
- Fork startup, funding, warm-up, command setup, and judge failures are trial errors. Broken pages and builds fail their checks.
- Harbor saves `/workspace` as an artifact, without `node_modules`, `dist`, `.git`, and `chain_context.json`. Leaving out the chain context symlink lets the publication secret check scan the saved project, since it rejects symlinks.

The wallet also supports atomic bundles and ERC-1271 signatures through an EIP-7702 account, for later page tasks.
The Savings wallet never offers atomic batching.

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

The free check runs no judge.
In its place, `solution-walk.mjs` walks our solution page through the same steps, so the code checks run.
It knows the solution's controls and runs only when the source matches the solution exactly.

Verifier self-tests run outside scored trials.
Install the pinned verifier packages in a directory you own, then run this command from the repository root:

```sh
T=tasks/build/aave-savings-page/tests
VERIFIER_DEPS=/path/to/verifier-packages \
  node --test $T/*.test.mjs
```

- The Node tests need Anvil and a Playwright Chromium installation.
- The package versions are in `environment/verifier/package.json`.
- Set `PLAYWRIGHT_BROWSERS_PATH` if your browser installation uses a custom directory.

To look at a saved project, open the trial's `artifacts/workspace/` directory and install dependencies from its lockfile.
For live chain access, add a `chain_context.json` file for your own fork.

### Copying the verifier to another page task

Each task owns its verifier files, and no task imports another task at runtime.

Copy these into the new task's `tests/`:

- `deps.mjs`, `rpc.mjs`, `rpc-policy.mjs`, `wallet.mjs`, `harness.mjs`, and `static-server.mjs`
- `stop-agent.py`, and the unprivileged build steps from `test.sh`
- `Wallet.sol` and `wallet-bytecode.txt`, if the task tests atomic bundles

What the copied files give you:

- `createHarness({workspace, output, sourceContext, funding, warm, externalBrowser})` creates the fork, funded account, browser, and static server. With `externalBrowser`, Playwright MCP opens the page instead.
- `warm(mainRpc)` is optional. It runs after funding and before the first snapshot, so the snapshot keeps the state it reads.
- `funding` supplies `nativeBalance` and token transfers, each with `token`, `holder`, and `amount`.
- The returned object exposes `mainRpc`, `account`, `sourceBlock`, `session`, `reset`, `capture`, and `close`.
- `session({atomic, beforeSend})` opens the built page and returns `page`, `context`, `wallet`, and `errors`.
- `reset()` closes that session and restores the funded snapshot.
- `close()` stops the browser, server, and fork.
- The wallet records requests before execution and transactions after mining.

What the new task supplies:

- Its session, commands, chain setup, funding addresses, and expected values. For Savings, those live in `session.mjs`, `chain.mjs`, and `checks.mjs`.
- Its judge file, prompt and page setup, like Savings' `page.toml`, `prompt.md` and `mcp-page.mjs`.
- A warm-up that reads the state the page touches, like Savings' `warm.mjs`. Without one, the first action to touch new state pays for every upstream read inside the judge's waits.
- Its own check names, and which failures are trial errors.
- The check-record and RewardKit wiring, adapted from `test.sh` and `run_reward.py`.

Keep state that only a check needs, like the full cap here, in the verifier's fork, so the agent builds against the real chain.

For the image:

- Copy `environment/verifier/`, including the lockfile and private font configuration.
- In the Dockerfile, copy Node and install pnpm, then copy this task's root-only verifier installation block. It downloads library packages, extracts them under `/root/savings-libs`, and installs Chromium without `--with-deps`.
- Keep the `COPY verifier/fonts.conf /root/savings-fonts.conf` line and the `chmod 700` paths, consistent with `deps.mjs`, `harness.mjs`, and `test.sh`.
- No shared-image change is needed.
