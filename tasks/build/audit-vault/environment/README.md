# Sluice

Sluice is a USDC yield vault. Users deposit USDC and receive slUSDC, an ERC-4626 share token with EIP-2612 permit. The vault keeps some USDC idle for withdrawals and supplies the rest to lending markets through strategies. The treasury earns a performance fee on what the strategies make and a small yearly management fee.

## How it works

- **Deposits and withdrawals.** `SluiceVault` is a standard ERC-4626 vault. `totalAssets()` is the vault's idle USDC plus what each active strategy held at its last harvest, less the fees owed to the treasury and profit that is still unlocking. We value strategies at their harvested value so that a market whose price moves inside a block can't move ours. A withdrawal is paid from idle USDC first; if that isn't enough, the vault pulls the rest from strategies in `withdrawQueue` order. `maxWithdraw` and `maxRedeem` are limited by what the strategies can return right now. `maxDeposit` and `maxMint` respect the deposit limit and return zero while the vault is paused.
- **Strategies.** Each strategy holds funds for one vault and supplies them to one market. `LendingMarketStrategy` supplies an ERC-4626 lending market. `AaveV3Strategy` supplies an Aave v3 reserve and holds its aToken. Only the vault can move a strategy's funds. `BaseStrategy` holds the bookkeeping both share.
- **Allocation.** Allocators move idle USDC into a strategy with `allocate`, up to the strategy's cap, and back with `deallocate`. `reallocate` takes a list of strategies and target sizes and moves each one in order, so allocators can shift funds between markets in one transaction. A target of `type(uint256).max` fills a strategy with all free idle USDC, up to its cap. USDC owed to the treasury is never allocated.
- **Harvest and fees.** Allocators call `harvest(strategy)` or `harvestAll()` about once a day. Harvest books what a strategy earned or lost and charges `performanceFee` (in basis points, at most 30%) on any gain. Interest earned since the last harvest stays in the market until harvest books it. Profit after the fee reaches the share price gradually over two days rather than in one step. A loss is taken from profit that is still unlocking first. The management fee (at most 2% a year) is charged on total assets for the time since it was last charged, on every deposit, withdrawal, harvest and claim. Both fees are booked in USDC as `accruedFees` and stay in the vault until anyone calls `claimFees()`, which pays them to the treasury.
- **Rewards.** Aave pays incentive rewards on some reserves. Allocators call `sellRewards(strategy, reward, minAssets)` to claim a strategy's rewards and sell them for USDC through `rewardSwapper`, a swap router the owner sets. The USDC stays idle until allocators supply it.
- **Timelock.** Changes that could hurt depositors wait for `timelock` (1 to 14 days): adding a strategy, raising a cap, raising a fee, shortening the timelock, and replacing the guardian. The role submits the change, and anyone can accept it once the wait is over. Changes that only lower risk apply at once: lowering a cap or a fee, lengthening the timelock, removing a strategy.
- **Guardian.** The guardian can pause the vault and revoke any pending change. Pausing stops deposits, `allocate` and `reallocate`. Withdrawals, `deallocate` and harvests keep working. Only the owner can unpause.

## Roles

| Role | Who | Trusted to |
| --- | --- | --- |
| Owner | Sluice multisig (4 of 7) | set the curator, allocators, guardian, treasury, reward swapper, fees and timelock; unpause. Also holds every curator and allocator power |
| Curator | Sluice risk team multisig (3 of 5) | submit strategies and caps, remove strategies, set the withdrawal order and the deposit limit. Also holds allocator powers |
| Allocators | Sluice bot and the risk team | allocate, deallocate, reallocate, harvest and sell rewards. Trusted to act on time and pick sensible targets, not to protect the vault from itself |
| Guardian | Security council (3 of 5, independent signers) | pause and revoke pending changes |
| Treasury | Sluice treasury multisig | receive fees |
| Depositors | anyone | nothing |

Markets are vetted by the curator before a strategy is submitted, and depositors can leave during the timelock if they disagree. Assume the markets are honest and can be short of liquidity when their borrowers use most of it. A market can also take bad debt when a borrower defaults. An Aave reserve can be frozen or paused by Aave governance. The reward swapper is trusted to fill at a fair price above `minAssets`.

## Scope

| File | What it is |
| --- | --- |
| `src/SluiceVault.sol` | the vault: shares, withdrawals, allocation, harvest, fees |
| `src/SluiceConfig.sol` | roles, timelocked settings, pause |
| `src/strategies/BaseStrategy.sol` | the bookkeeping every strategy shares |
| `src/strategies/LendingMarketStrategy.sol` | the strategy for an ERC-4626 lending market |
| `src/strategies/AaveV3Strategy.sol` | the strategy for an Aave v3 reserve |
| `src/tokens/ERC20.sol` | the share token, with permit |
| `src/interfaces/*.sol` | interfaces, including the Aave rewards controller and the swapper |

Out of scope: `test/`, including the mock markets.

Deployment: Ethereum mainnet and Base. The asset is USDC only. Fee-on-transfer and rebasing tokens will never be used.

## Known issues

- If a market has lent out most of its cash, withdrawals that need that strategy revert with `InsufficientLiquidity` until borrowers repay. Users can withdraw up to `maxWithdraw`. The same holds while an Aave reserve is paused.
- `withdrawQueue` is iterated on every deposit and withdrawal. We cap it at 10 strategies, so gas use is bounded.
- ERC-4626 conversions round in the vault's favour, so a depositor can lose up to 1 wei of USDC per deposit or withdrawal.
- The vault is deployed with a timelock of zero so we can add the first strategies in one go. The owner sets the real timelock before deposits open.
- `removeStrategy` pulls everything out of the market and reverts if the market can't return it all. The curator lowers the cap to zero and deallocates first.
- `reallocate` runs the steps in the order given. A plan that supplies a strategy before freeing the USDC for it reverts with `InsufficientIdle`.

## Build

```sh
forge build
forge test
```
