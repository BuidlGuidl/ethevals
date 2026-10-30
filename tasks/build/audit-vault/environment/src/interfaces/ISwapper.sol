// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

/// @notice A swap router the vault sells incentive rewards through.
interface ISwapper {
    /// @notice Sells `amountIn` of `tokenIn`, pulled from the caller, for at least `minAmountOut` of `tokenOut`.
    /// @return amountOut The `tokenOut` sent to `receiver`.
    function swap(address tokenIn, address tokenOut, uint256 amountIn, uint256 minAmountOut, address receiver)
        external
        returns (uint256 amountOut);
}
