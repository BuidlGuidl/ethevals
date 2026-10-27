// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

interface IPriceFeed {
    /// @notice Anyone can read the USDC value of one TKN, expressed with 18 decimals.
    /// @dev Reverts when the feed cannot price TKN.
    function price() external view returns (uint256);
}
