# Aave savings page

The user asks for a Savings page for USDC and USDT on Aave v3.
The verifier drives the page with an injected wallet on a local fork.
It checks visible values, wallet requests, and the resulting chain balances.

## The instruction

```text
Our users hold USDC and USDT on Ethereum mainnet and want to earn on them without leaving our app. Add a Savings page to this project where a connected user can deposit either token into Aave v3, see how much they have deposited including interest so far and the current APY, and withdraw part or all of it at any time. The chain to use is in `chain_context.json`.
```

## What it touches

The agent starts in `/workspace` with the create-wagmi 2.0.19 vite-react project.
Its lockfile pins wagmi 3.7.9, viem 2.57.11, React 19.3.1, and Vite 8.3.5.
The main image adds Node.js 22 and pnpm 9.14.2 to the shared Debian chain image.
It installs project dependencies from the lockfile during the image build.
The project needs no npm download during a trial.
The image includes curl, bash, procps, and ripgrep for Harbor's agent installers.
Harbor can still download the selected agent CLI during setup.

The chain forks Ethereum mainnet at block `26260992`, dated 2026-10-24 at 07:25:11 UTC.
This was a finalized block when checked.
At that block, Aave v3's main pool has active, unfrozen, unpaused USDC and USDT reserves.
The pool is `0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2`.
Only the chain sidecar receives `MAINNET_RPC_URL`.
Setup leaves the reserve configuration and block clock unchanged, without funding any wallet.
The task chain exposes the real market at the pinned block.
Setup writes the chain context.
The agent reads `/workspace/chain_context.json` through the existing read-only chain context link.

The task's main image installs Playwright 1.61.1, Chromium, and viem 2.57.11 under root-only directories.
It extracts Chromium's added shared libraries under `/root/savings-libs` instead of installing them system-wide.
Only the verifier's browser launch receives that library path.
An agent-downloaded Chromium cannot launch with the system libraries alone.
The verifier starts its own Anvil fork of the task chain after the agent stops.
Before the cap journey, it lowers USDC's supply cap through the pool configurator in that fork alone.
It impersonates the provider's ACL admin after checking its pool admin role.
That governance contract has no ETH, so the next block's base fee and transaction gas price are zero.
The cap is the aUSDC total supply rounded up to whole USDC, plus 5,000 USDC.
Aave also counts accrued treasury tokens against the cap, which leaves less than 5,000 USDC of room.
A deposit above the room fails with `SupplyCapExceeded()` and selector `0xf58f733a`.
Pool revision 11 uses this custom error in place of the older string error `51`.
The verifier fixes its fork's block interval at zero and advances time only where a journey needs it.
The cap journey keeps a stable clock; other journeys use the original cap.
It funds a fresh wallet with ETH and 10,000 units of each token through local chain controls.
The private key stays in the verifier process and never enters the page or public chain context.
Playwright injects an EIP-1193 provider and announces it through EIP-6963.
Browser JSON-RPC reads, including `/rpc` requests and Docker hostnames, reach the verifier's fork through request routing.
The verifier does not change the agent's source.
The page and wallet share a read allowlist that mirrors the task chain, excluding raw transaction submission.
Other browser endpoints and WebSockets are blocked.
The verifier kills leftover agent processes before building and again before starting its fork.
Both compile commands run as `agent`, with verifier credentials removed from their environment.
The verifier serves built files with its own static server, without loading Vite configuration.

The main container gets one CPU and 4 GiB of memory.
The chain sidecar has a 3 GiB memory limit.
The task adds no agent time limit.

## The checks

Harbor saves `/workspace` as an artifact, excluding `node_modules`, `dist`, `.git`, and `chain_context.json`.
The saved project contains plain files that the publication secret check can scan.
The exclusion removes the chain context symlink, which the secret check rejects.
The verifier runs both compile commands and writes `build.log`, `typecheck.log`, and `checks.json` under `/logs/verifier/`.
It copies `/opt/check_records.py` into `/tests/check_records.py`.
RewardKit uses this shared adapter to turn `checks.json` into named checks and the reward.
The browser opens the production build through the verifier's static server.
It finds token cards or rows by their visible text, then uses accessible control names and amount inputs.
Missing controls fail the affected checks with `could not drive: ...` and a screenshot.
Each journey saves page text, a screenshot, and wallet requests with transaction receipts.
Snapshots isolate the USDT and supply-cap journeys.
After the USDC deposit, the verifier advances time by 30 days and reloads the page to check accrued interest.
Withdrawal requests advance another day before mining, so a Max control that sends a balance snapshot leaves dust.
Each withdrawal journey gets a funded position if its preceding journey fails.
The APY check runs before any deposit action.
Fork startup, funding, and invalid fixtures cause trial errors.
Broken pages and builds fail their affected checks.

| Check | What it proves | Area | Instruction words | Reference code |
| --- | --- | --- | --- | --- |
| `compile` | Both build and type check succeed | frontend compilation | "Add a Savings page to this project" | Project build script and `tsc` in [test.sh](tests/test.sh) |
| `deposit_usdc` | Depositing 100 USDC leaves 100 aUSDC within 0.01 USDC | Aave supply | "deposit either token into Aave v3" | Aave [SupplyLogic.executeSupply](https://github.com/aave-dao/aave-v3-origin/blob/8305565ae342f1773c42cd2e4593f175fe5968a0/src/contracts/protocol/libraries/logic/SupplyLogic.sol) |
| `shows_deposit` | The visible balance matches accrued aUSDC within 0.01 USDC | interest-inclusive balance | "including interest so far" | Aave [AToken.balanceOf](https://github.com/aave-dao/aave-v3-origin/blob/8305565ae342f1773c42cd2e4593f175fe5968a0/src/contracts/protocol/tokenization/AToken.sol) |
| `shows_apy` | The labelled APY matches per-second compounding within 0.01 percentage points | Aave rates | "the current APY" | Aave [formatReserve](https://github.com/aave/aave-utilities/blob/2d0db501009fdb34824cbc9a486c3e9fd7191ec7/packages/math-utils/src/formatters/reserve/index.ts), compared by [reserve()](tests/chain.mjs) |
| `withdraw_partial` | Withdrawing returns 40 USDC and reduces the accrued position by that amount | Aave withdrawal | "withdraw part ... at any time" | Aave [SupplyLogic.executeWithdraw](https://github.com/aave-dao/aave-v3-origin/blob/8305565ae342f1773c42cd2e4593f175fe5968a0/src/contracts/protocol/libraries/logic/SupplyLogic.sol) |
| `withdraw_all` | Max returns the whole position and leaves exactly zero aUSDC | closing a position | "withdraw ... all of it at any time" | `executeWithdraw`'s [max-uint branch](https://github.com/aave-dao/aave-v3-origin/blob/8305565ae342f1773c42cd2e4593f175fe5968a0/src/contracts/protocol/libraries/logic/SupplyLogic.sol#L124) |
| `deposit_usdt_leftover_allowance` | Depositing 100 USDT succeeds with an existing 1 USDT Pool allowance | token approvals | "deposit either token" | USDT's verified [approve implementation](https://etherscan.io/address/0xdac17f958d2ee523a2206206994597c13d831ec7#code) |
| `refuses_over_cap` | When Aave would refuse the deposit, the page asks the wallet for nothing | Aave supply cap | "deposit either token into Aave v3" | Aave [SupplyModalContent.tsx](https://github.com/aave/interface/blob/ae94b94ccdc4f370c53c4c78111413ce9790eb1e/src/components/transactions/Supply/SupplyModalContent.tsx#L187-L196), [validateSupply](https://github.com/aave-dao/aave-v3-origin/blob/8305565ae342f1773c42cd2e4593f175fe5968a0/src/contracts/protocol/libraries/logic/ValidationLogic.sol) |
| `explains_supply_cap` | The page explains the refused deposit's cap in words | user feedback, judge | "deposit either token into Aave v3" | [cap-explanation.toml](tests/cap-explanation.toml) and Aave's supply UI above |
| `switches_and_continues` | Deposit or Withdraw switches to Ethereum and carries on without another click | network handling, judge | "Ethereum mainnet" and "The chain to use is in `chain_context.json`" | [network-flow.toml](tests/network-flow.toml) |

The reward is 1 only when every check passes.
The cap check fails any wallet write request, including an approval alone, regardless of the Pool entry point.
It waits for three seconds of wallet inactivity, with a twenty-second ceiling.
A pending request at that ceiling still counts as asked.
Disabled, missing, or relabelled controls after typing count as no wallet request.
The same page must first complete an in-room deposit.
A page can simulate the whole supply before its first wallet prompt; no explicit cap read is required.
Clamping the typed amount to the room still fails if the page asks the wallet for a write.
It measures the current reserve configuration and includes accrued treasury tokens in the remaining room.
The room bounds and oversized amount live in `capFixture()` in `tests/chain.mjs`.
The reusable wallet still supports atomic bundles and ERC-1271 signatures through an EIP-7702 account.
Savings runs no atomic journey or observation; its extra page drive and settling time add verifier cost.

The board-only RewardKit judge reads `cap-page.txt` and `cap-page.png`, alongside the required guarded trajectory.
It checks whether the page explains the supply cap rather than showing a generic failure or selector.
A second judge reads a source snapshot with file paths, excluding dependencies and build output.
It follows Deposit or Withdraw through a network switch and the transaction that follows.
Free checks and PR CI skip both paid criteria.

## Why it matters

A compiling project alone gives no evidence that its Savings page works.
These checks exercise the wallet and Aave contracts behind the page's controls.
Aave's [supply guide](https://aave.com/help/supplying/supply-tokens) describes interest accruing in the supplied balance.
Its [withdrawal guide](https://aave.com/help/supplying/withdraw-tokens) describes the liquidity requirement for withdrawals.

## Notes

`solution/solve.sh` installs a Savings page based on the claude-2 discovery trial.
It adds atomic calls to that page's deposits.
The untouched starting project compiles but has no Savings controls, so its browser checks fail.

The environment files hold the project, image definitions, and chain setup.
The tests directory holds the browser journeys, wallet, compile commands, and RewardKit settings.
The solution directory holds the working page.

With `MAINNET_RPC_URL` set, run the free check from the repository root:

```sh
uv run ethevals lint --tasks tasks/building/aave-savings-page
uv run ethevals free-check --tasks tasks/building/aave-savings-page --output /tmp/aave-savings-free-check
```

Verifier self-tests run outside scored trials.
Install the pinned verifier packages in a directory you own, then run these commands from the repository root:

```sh
VERIFIER_DEPS=/path/to/verifier-packages node --test tasks/building/aave-savings-page/tests/*.test.mjs
python3 tasks/building/aave-savings-page/tests/test_source_snapshot.py
```

The Node tests need Anvil and a Playwright Chromium installation.
The package versions are in `environment/verifier/package.json`.
Set `PLAYWRIGHT_BROWSERS_PATH` if your browser installation uses a custom directory.

### Copying the verifier to another page task

Each task owns its verifier files; no task imports another task at runtime.
Copy `deps.mjs`, `rpc.mjs`, `rpc-policy.mjs`, `wallet.mjs`, `harness.mjs`, `static-server.mjs`, and `control-vocabulary.mjs` into the new `tests/`.
Copy `stop-agent.py` and the unprivileged build steps from `test.sh` too.
If the task tests atomic bundles, copy `Wallet.sol` and `wallet-bytecode.txt`.
`createHarness({workspace, output, sourceContext, funding})` creates the fork, funded account, browser, and static server.
`funding` supplies `nativeBalance` and token transfers, each with `token`, `holder`, and `amount`.
The returned object exposes `mainRpc`, `account`, `sourceBlock`, `session`, `reset`, `capture`, and `close`.
`session({atomic, beforeSend})` returns `page`, `context`, `wallet`, and `errors` after opening the built page.
`reset()` closes that session and restores the funded snapshot.
`close()` stops the browser, server, and fork.
The wallet records requests before execution and transactions after mining.
`createVocabulary(words, {prerequisites})` supplies matching and submission helpers for the new task's action words.

Supply the new task's journeys, chain setup, funding addresses, expected values, and page-specific control scopes.
For Savings, those live in `browser.mjs`, `chain.mjs`, `controls.mjs`, and `environment/setup/`.
Copy and adapt the check-record and RewardKit wiring in `test.sh`.
The new task must define its own check names and decide which failures are trial errors.

Copy `environment/verifier/`, including the lockfile and private font configuration.
In the Dockerfile, copy Node and install pnpm, then copy the root-only verifier installation block from this task.
That block downloads library packages, extracts them under `/root/savings-libs`, and installs Chromium without `--with-deps`.
Keep the `COPY verifier/fonts.conf /root/savings-fonts.conf` line and the `chmod 700` paths.
Keep those paths consistent with `deps.mjs`, `harness.mjs`, and `test.sh`.
No shared-image change is needed.

To run either free agent directly through Harbor:

```sh
uv run harbor run -p tasks/building/aave-savings-page -a oracle -e docker --n-concurrent 1
uv run harbor run -p tasks/building/aave-savings-page -a nop -e docker --n-concurrent 1
```

To inspect a saved project, open the trial's `artifacts/workspace/` directory and install dependencies from its lockfile.
For live chain access, add a `chain_context.json` file for your own fork.
