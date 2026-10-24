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
Setup lowers USDC's supply cap through the pool configurator.
It impersonates the provider's ACL admin after checking its pool admin role.
That governance contract has no ETH.
Setup sets the next block's base fee and the transaction's gas price to zero.
The cap is the aUSDC total supply rounded up to whole USDC, plus 5,000 USDC.
Aave also counts accrued treasury tokens against the cap.
The actual deposit room is smaller than 5,000 USDC.
At this fork, more than 3,000 USDC remains available, so a 100 USDC deposit fits.
A deposit above the room fails with `SupplyCapExceeded()` and selector `0xf58f733a`.
Pool revision 11 uses this custom error in place of the older string error `51`.
The page must refuse an oversized supply before asking the wallet to send it.
Setup pins Anvil's block timestamp interval to zero before changing the cap.
Transactions keep the fork timestamp, so interest cannot consume the room during an hour of wall-clock time.
This also fixes USDT's interest clock, but setup leaves its reserve configuration unchanged.
Setup writes the chain context without funding any wallet.
The agent reads `/workspace/chain_context.json` through the existing read-only chain context link.

The task's main image installs Playwright 1.61.1, Chromium, and viem 2.57.11 under root-only directories.
The agent cannot run that browser installation.
The verifier starts its own Anvil fork of the task chain after the agent stops.
It funds a fresh wallet with ETH and 10,000 units of each token through local chain controls.
The private key stays in the verifier process and never enters the page or public chain context.
Playwright injects an EIP-1193 provider and announces it through EIP-6963.
Browser JSON-RPC reads, including `/rpc` requests and Docker hostnames, reach the verifier's fork through request routing.
The verifier does not change the agent's source.

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
The browser opens the production build through Vite preview.
It finds token cards or rows by their visible text, then uses accessible control names and amount inputs.
Missing controls fail the affected checks with `could not drive: ...` and a screenshot.
Each journey saves page text, a screenshot, and wallet requests with transaction receipts.
Snapshots isolate the USDT, supply-cap, and atomic-wallet journeys.
The withdrawal journey gets a funded position even if the page's deposit fails.

| Check | What it proves | Area |
| --- | --- | --- |
| `compile` | `pnpm build` and `pnpm exec tsc --noEmit` both exit successfully | frontend compilation |
| `deposit_usdc` | A 100 USDC deposit through the page leaves 100 aUSDC within 0.01 USDC | Aave supply |
| `shows_deposit` | The visible USDC deposit matches the wallet's aToken balance within 0.01 USDC | interest-inclusive balance |
| `shows_apy` | The visible USDC APY matches the reserve's per-second compounded rate within 0.01 percentage points | Aave rates |
| `withdraw_partial` | A 40 USDC withdrawal leaves 60 aUSDC within 0.01 USDC | Aave withdrawal |
| `withdraw_all` | The page's Max or equivalent withdraw-all control leaves exactly zero aUSDC | closing a position |
| `deposit_usdt_leftover_allowance` | A 100 USDT deposit succeeds with an existing 1 USDT Pool allowance | token approvals |
| `refuses_over_cap` | An amount above the chain's remaining room causes no doomed supply request to the wallet | Aave supply cap |
| `atomic_deposit` | An atomic-capable wallet completes a USDC deposit through one bundle or a permit and one supplyWithPermit transaction | wallet capabilities |
| `explains_supply_cap` | The saved page explains the refused deposit's supply cap in words | user feedback, judge |
| `switches_and_continues` | The source shows that Deposit and Withdraw switch to Ethereum and continue the original action without another click | network handling, judge |

The reward is 1 only when every check passes.
The cap check permits approval requests and simulations that refuse the supply before the wallet opens.
It measures the current reserve configuration and includes accrued treasury tokens in the remaining room.
The atomic journey starts with no allowance and advertises `atomic.status = supported` through `wallet_getCapabilities`.
It uses an EIP-7702 account whose calls execute atomically in one mined transaction.
The account also validates ERC-1271 signatures so USDC permits work for the delegated wallet.
The wallet records separate transactions too, so a bundle implemented as sequential transactions cannot pass.

The board-only RewardKit judge reads `cap-page.txt` and `cap-page.png`, alongside the required guarded trajectory.
It checks whether the page explains the supply cap rather than showing a generic failure or selector.
A second judge reads a source snapshot with file paths, excluding dependencies and build output.
It follows the Deposit and Withdraw handlers through a network switch and the transaction that follows.
Free checks and PR CI skip both paid criteria.

## Why it matters

A compiling project alone gives no evidence that its Savings page works.
These checks exercise the wallet and Aave contracts behind the page's controls.
Aave's [supply guide](https://aave.com/help/supplying/supply-tokens) describes interest accruing in the supplied balance.
Its [withdrawal guide](https://aave.com/help/supplying/withdraw-tokens) describes the liquidity requirement for withdrawals.
The wallet API's [atomic capability](https://eips.ethereum.org/EIPS/eip-5792) lets a page combine approval and supply in one transaction.

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

To run either free agent directly through Harbor:

```sh
uv run harbor run -p tasks/building/aave-savings-page -a oracle -e docker --n-concurrent 1
uv run harbor run -p tasks/building/aave-savings-page -a nop -e docker --n-concurrent 1
```

To inspect a saved project, open the trial's `artifacts/workspace/` directory and install dependencies from its lockfile.
For live chain access, add a `chain_context.json` file for your own fork.
