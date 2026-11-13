// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

/// @notice What a branch's TroveManager and BorrowerOperations call for the collateral's price.
interface IPriceFeed {
    /// @notice USD price of one unit of this branch's collateral, 18 decimals,
    ///         for opening, adjusting and liquidating Troves.
    /// @return price The price to use now.
    /// @return oracleBroken True when this call found the oracle unusable.
    ///         BorrowerOperations then stops new borrowing on the branch.
    function fetchPrice() external returns (uint256 price, bool oracleBroken);

    /// @notice The price redemptions use, same units.
    function fetchRedemptionPrice() external returns (uint256 price, bool oracleBroken);
}
