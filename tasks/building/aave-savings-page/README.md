# Aave savings page

The user asks for a Savings page for USDC and USDT on Aave v3.
This folder is a discovery harness, not a finished task.
It checks only compilation and exports the project for human review.

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
Setup writes the chain context without funding any wallet or changing protocol state.
The agent reads `/workspace/chain_context.json` through the existing read-only chain context link.

The main container gets one CPU and 4 GiB of memory.
The chain sidecar has a 3 GiB memory limit.
The task adds no agent time limit.

## The checks

The shared verifier first writes `/logs/verifier/project.tar.gz` from `/workspace`.
The archive excludes `node_modules`, `dist`, and `.git` directories.
It preserves the chain context link and saves its JSON separately as `/logs/verifier/chain_context.json`.
The verifier then runs both compile commands and writes `build.log` and `typecheck.log` beside the archive.
RewardKit turns `checks.json` into the single named check and the reward.

| Check | What it proves | Area |
| --- | --- | --- |
| `compile` | `pnpm build` and `pnpm exec tsc --noEmit` both exit successfully | frontend compilation |

The reward is 1 when `compile` passes.
There are no judge criteria or browser checks.
The verifier does not check deposits, withdrawals, balances, APY, or wallet behavior.

## Why it matters

Discovery trials collect implementations before we choose checks for frontend behavior.
A compiling project alone gives no evidence that its Savings page works.
Aave's [supply guide](https://aave.com/help/supplying/supply-tokens) describes interest accruing in the supplied balance.
Its [withdrawal guide](https://aave.com/help/supplying/withdraw-tokens) describes the liquidity requirement for withdrawals.
Human review can use those requirements when choosing later checks.

## Notes

`solution/solve.sh` leaves the project untouched.
It only demonstrates that the discovery verifier accepts the initial project.
Both oracle and nop therefore pass `compile`.
ETH Evals free-check requires nop to fail, so it reports that expected failure after both trials finish.
This folder must gain behavior checks and a working Savings solution before it becomes a finished task.

The environment files hold the project, image definitions, and chain setup.
The tests directory holds the compile commands and RewardKit settings.
The solution directory holds the temporary no-op solution.

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

To inspect a saved project, extract its archive and install dependencies from its lockfile.
For live chain access, replace the extracted chain context link with a JSON file for your own fork.
The saved context uses the trial's internal `http://chain:8545` address.
