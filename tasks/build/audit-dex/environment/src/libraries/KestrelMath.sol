// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

/// @notice Constant-product pricing helpers shared by the vault and the router.
library KestrelMath {
    uint256 internal constant BPS = 10_000;

    error InsufficientInput();
    error InsufficientLiquidity();

    /// @notice Output for an exact input, after the pool's swap fee.
    /// @param amountIn Tokens delivered to the pool.
    /// @param reserveIn Pool reserve of the input token.
    /// @param reserveOut Pool reserve of the output token.
    /// @param feeBps Swap fee in basis points.
    function getAmountOut(uint256 amountIn, uint256 reserveIn, uint256 reserveOut, uint256 feeBps)
        internal
        pure
        returns (uint256)
    {
        if (amountIn == 0) revert InsufficientInput();
        if (reserveIn == 0 || reserveOut == 0) revert InsufficientLiquidity();
        uint256 amountInWithFee = amountIn * (BPS - feeBps);
        return (amountInWithFee * reserveOut) / (reserveIn * BPS + amountInWithFee);
    }

    /// @notice Amount of token B worth `amountA` of token A at the current reserve ratio.
    function quote(uint256 amountA, uint256 reserveA, uint256 reserveB) internal pure returns (uint256) {
        if (amountA == 0) revert InsufficientInput();
        if (reserveA == 0 || reserveB == 0) revert InsufficientLiquidity();
        return (amountA * reserveB) / reserveA;
    }

    /// @notice Babylonian square root, rounded down.
    function sqrt(uint256 y) internal pure returns (uint256 z) {
        if (y > 3) {
            z = y;
            uint256 x = y / 2 + 1;
            while (x < z) {
                z = x;
                x = (y / x + x) / 2;
            }
        } else if (y != 0) {
            z = 1;
        }
    }

    function min(uint256 a, uint256 b) internal pure returns (uint256) {
        return a < b ? a : b;
    }
}
