# Sluice

Sluice is a USDC yield vault. Users deposit USDC and receive slUSDC, an ERC-4626 share token. The vault keeps some USDC idle for withdrawals and supplies the rest to lending markets through strategies. The treasury earns a performance fee on the interest the strategies make.

## How it works

- **Deposits and withdrawals.** `SluiceVault` is a standard ERC-4626 vault. `totalAssets()` is the vault's idle USDC plus the live value of every active strategy. A withdrawal is paid from idle USDC first; if that isn't enough, the vault pulls the rest from strategies in `withdrawQueue` order.
- **Strategies.** Each strategy holds funds for one vault and supplies them to one ERC-4626 lending market (`LendingMarketStrategy`). Only the vault can move a strategy's funds.
- **Allocation.** The keeper moves idle USDC into a strategy with `allocate`, up to the strategy's cap, and back with `deallocate`.
- **Harvest and fees.** The keeper calls `harvest(strategy)` on a schedule, about once a day per strategy. Harvest books the profit or loss the strategy made since its last harvest. On profit, the vault books `performanceFee` (in basis points, at most 30%) of the profit as `accruedFees`. The fee stays in the vault as USDC until anyone calls `claimFees()`, which pays it to the treasury.

## Promises

1. The treasury earns `performanceFee` of the interest the strategies earn.
2. The share price never falls except when a strategy loses money.
3. A depositor can always withdraw up to the liquidity the vault and its strategies have free.
4. Only the vault can move funds held by a strategy.

## Roles

| Role | Who | Trusted to |
| --- | --- | --- |
| Owner | Sluice multisig (4 of 7) | add and remove strategies, set caps, the fee, the deposit limit, the keeper and the treasury; pause deposits |
| Keeper | Sluice bot | allocate, deallocate and harvest. Trusted to act on time, not to protect the vault from itself |
| Treasury | Sluice treasury multisig | receive fees |
| Depositors | anyone | nothing |

The lending markets are vetted by the owner before a strategy is added. Assume they are honest ERC-4626 vaults that can be short of liquidity when their borrowers use most of it.

## Scope

| File | What it is |
| --- | --- |
| `src/SluiceVault.sol` | the vault: shares, withdrawals, allocation, harvest, fees |
| `src/strategies/BaseStrategy.sol` | the bookkeeping every strategy shares |
| `src/strategies/LendingMarketStrategy.sol` | the strategy that supplies one ERC-4626 lending market |
| `src/tokens/ERC20.sol` | the share token |
| `src/interfaces/*.sol` | interfaces |

Out of scope: `test/`, including the mock lending market.

Deployment: Ethereum mainnet and Base. The asset is USDC only. Fee-on-transfer and rebasing tokens will never be used.

## Known issues

- If a lending market has lent out most of its cash, withdrawals that need that strategy revert with `InsufficientLiquidity` until borrowers repay. Users can withdraw up to `maxWithdraw`.
- A loss in a lending market is shared by all depositors as soon as `totalAssets()` sees it. We do not protect early leavers or late leavers against it.
- `withdrawQueue` is iterated on every deposit and withdrawal. We cap it at 10 strategies, so gas use is bounded.
- ERC-4626 conversions round in the vault's favour, so a depositor can lose up to 1 wei of USDC per deposit or withdrawal.

## Build

```sh
forge build
forge test
```
