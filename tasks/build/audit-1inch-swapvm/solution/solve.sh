#!/bin/sh
set -eu
cat > /workspace/findings.md <<'REPORT'
# SwapVM findings

## 1. PeggedSwapMath.solve loses precision for small linearWidth

Severity: Critical

Location: src/libs/PeggedSwapMath.sol (solve); src/instructions/PeggedSwap.sol (_peggedSwapGrowPriceRange2D)

solve computes w = (sqrt(D) - 1) / (2a) with D = 1 + 4*a*rightSide. For a small linearWidth a, D is close to 1 and sqrt(D) - 1 cancels almost all significant digits, so the output reserve v = w^2 comes out wrong. The maker pays out more than the curve allows and the invariant drops; a single crafted swap can take a large share of the pool, and repeated swaps take more. Use the stable form w = 2*rightSide / (1 + sqrt(D)).

## 2. Multi-token XYCConcentrate orders share one liquidity value across pairs

Severity: Critical

Location: src/instructions/XYCConcentrate.sol (_xycConcentrateGrowLiquidityXD, _updateScales, concentratedBalance)

liquidity[orderHash] is one value per order, and _updateScales overwrites it with sqrt((balanceIn + amountIn) * (balanceOut - amountOut)) for the pair just traded. With three tokens, the next swap on a different pair scales its virtual balances with the previous pair's liquidity. Trading A to B, B to C, then C to A at the distorted rates returns more A than was put in, and repeating it drains the order.

## 3. PeggedSwap normalizes balances on the wrong axes for reverse swaps

Severity: Critical

Location: src/instructions/PeggedSwap.sol (_peggedSwapGrowPriceRange2D)

x0 and y0 are balanceIn and balanceOut, which follow the swap direction, but they are normalized by config.x0 and config.y0, which follow token address order. When tokenIn has the higher address, each balance is divided by the other token's capacity. With unequal capacities the invariant comes out far too high and the solver gives away far too much of the output token, draining the pool.

## 4. XYCConcentrate records liquidity without the output-side protocol fee

Severity: High

Location: src/instructions/XYCConcentrate.sol (_updateScales); src/instructions/FeeExperimental.sol (_aquaProtocolFeeAmountOutXD, _feeAmountOut); src/strategies/AquaAMM.sol (buildProgram)

AquaAMM places _xycConcentrateGrowLiquidity2D before _aquaProtocolFeeAmountOutXD. The fee instruction lets the swap compute the gross output, resets amountOut to the taker's net amount and pulls the fee from the maker's Aqua balance. _updateScales then records liquidity from the net amountOut, so the fee that left the maker is never subtracted. Each fee-paying swap pushes the recorded liquidity further above the real reserves, and the order quotes swaps it cannot fill.

## 5. Dynamic balances overstate tokenIn when an input-side protocol fee is paid out at once

Severity: High

Location: src/instructions/Balances.sol (_dynamicBalancesXD); src/instructions/Fee.sol (_dynamicProtocolFeeAmountInXD, _feeAmountIn)

_dynamicBalancesXD adds the returned swapAmountIn to the stored tokenIn balance. When it wraps _dynamicProtocolFeeAmountInXD, _feeAmountIn leaves amountIn at the gross value while the fee is transferred from the maker to the fee recipient. The stored balance rises by 1000 when the maker kept 990, the error grows with every swap, and later prices are computed from balances the maker does not have.
REPORT
