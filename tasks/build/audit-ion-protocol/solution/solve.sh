#!/bin/sh
set -eu
cat > /workspace/findings.md <<'REPORT'
# Ion Protocol findings

## 1. Anyone can set the reserve feed's exchange rates

Severity: Critical

Location: src/oracles/reserve/ReserveFeed.sol (setExchangeRate); src/oracles/reserve/ReserveOracle.sol

ReserveFeed.setExchangeRate has no access control and no input validation. Any address can write any exchange rate for any ilk index. The reserve oracles read FEED0 and FEED1 from this contract and take the minimum with the protocol rate, and the Liquidation contract values collateral with that rate. An attacker sets a collateral's rate near zero, updates the reserve oracle, and liquidates healthy vaults.

## 2. zapRepay charges the caller twice and strands the WETH

Severity: Critical

Location: src/periphery/IonZapper.sol (zapRepay)

zapRepay wraps msg.value into WETH held by the zapper, then calls POOL.repay(ilkIndex, msg.sender, msg.sender, ...). The third argument is the payer, so IonPool pulls WETH from the caller instead of the zapper. A caller with a WETH allowance to the pool pays the debt from their WETH and also loses the ETH they sent, which stays in the zapper as WETH. The zapper has no function to recover it.

## 3. Full repayments through the handlers revert

Severity: High

Location: src/flash/handlers/base/IonHandlerBase.sol (repayAndWithdraw, _repayAndWithdraw)

repayAndWithdraw takes debtToRepay in WETH, fixed when the user signs. _repayAndWithdraw divides it by the rate after accrual at execution time. When the user tries to repay everything, interest accrued before mining and rounding make the normalized amount either larger than the vault's normalized debt, so the debt update underflows and reverts, or slightly smaller, leaving dust below the ilk's dust limit, which reverts. There is no max-repay option, so closing a position this way almost always fails.

## 4. zapDepositWstEth never approves the tokens it moves

Severity: High

Location: src/periphery/IonZapper.sol (zapDepositWstEth)

The function transfers stETH in, calls WSTETH.wrap and then WSTETH_JOIN.join. wrap pulls stETH from the zapper and join pulls wstETH from the zapper, but the zapper never approves either contract. Both calls revert, so the stETH deposit path is unusable.

## 5. The reserve oracle's change limit applies per call only

Severity: High

Location: src/oracles/reserve/ReserveOracle.sol (updateExchangeRate)

updateExchangeRate bounds the new rate to MAX_CHANGE around the stored currentExchangeRate, but it is public and has no time or block limit. Calling it several times in one transaction moves the stored rate by MAX_CHANGE each time until it reaches the minimum of the feeds and the protocol rate. Anyone who can move a feed or the provider's rate can crash the rate in one transaction and liquidate vaults, since liquidations use this rate.

## 6. The swETH TWAP pool cannot serve the averaging window

Severity: High

Location: src/oracles/spot/SwEthSpotOracle.sol (getPrice); src/libraries/uniswap/UniswapOracleLibrary.sol (consult)

getPrice calls consult on the mainnet swETH/ETH 0.05% Uniswap v3 pool (0x30eA22C879628514f1494d4BBFEF79D21A6B49A2) with SECONDS_AGO. That pool's observation cardinality is far below what a window of about two hours needs (around 600 observations), and neither the constructor nor getPrice checks it or calls increaseObservationCardinalityNext. observe then reverts with OLD, getSpot reverts, and every vault action that checks the spot price fails, so swETH borrowers cannot repay or add collateral while liquidations, which use the reserve rate, still proceed.
REPORT
