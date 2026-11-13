// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

/// @notice A fee module sets the swap fee of the pools at the fee tier it is attached to.
interface IKestrelFeeModule {
    /// @notice Swap fee for `poolId` right now, in basis points of the input.
    function swapFee(bytes32 poolId) external view returns (uint256);
}
