// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

interface IMarket {
    /// @notice Anyone can supply assets in USDC base units, credited to onBehalf.
    function supply(uint256 assets, address onBehalf) external;
    /// @notice Lenders can withdraw their own supply in USDC base units to to.
    function withdraw(uint256 assets, address to) external;
    /// @notice Anyone can supply assets in TKN base units, credited to onBehalf.
    function supplyCollateral(uint256 assets, address onBehalf) external;
    /// @notice Borrowers can withdraw their own collateral in TKN base units to to.
    function withdrawCollateral(uint256 assets, address to) external;
    /// @notice Borrowers can borrow assets in USDC base units against their collateral, paid to to.
    function borrow(uint256 assets, address to) external;
    /// @notice Anyone can repay assets in USDC base units for onBehalf.
    function repay(uint256 assets, address onBehalf) external;
    /// @notice Anyone can repay a liquidatable borrower's USDC debt and receive TKN collateral.
    /// @param repayAssets The requested repayment in USDC base units.
    /// @return seizedCollateral The TKN base units received by the caller.
    function liquidate(address borrower, uint256 repayAssets) external returns (uint256 seizedCollateral);
    /// @notice Anyone can read account's current debt, including interest, in USDC base units.
    function borrowBalance(address account) external view returns (uint256);
    /// @notice Anyone can read account's current supply, including interest, in USDC base units.
    function supplyBalance(address account) external view returns (uint256);
    /// @notice Anyone can read account's collateral in TKN base units.
    function collateralBalance(address account) external view returns (uint256);
    /// @notice Anyone can read whether account's debt is within its collateral borrowing limit.
    function isHealthy(address account) external view returns (bool);
    /// @notice Anyone can read total current supplied assets in USDC base units.
    function totalSupplyAssets() external view returns (uint256);
    /// @notice Anyone can read total current borrowed assets in USDC base units.
    function totalBorrowAssets() external view returns (uint256);
    /// @notice Anyone can read the supply cap in USDC base units.
    function supplyCap() external view returns (uint256);
    /// @notice Anyone can read the collateral cap in TKN base units.
    function collateralCap() external view returns (uint256);
    /// @notice Anyone can read the treasury fee in basis points of borrower interest.
    function fee() external view returns (uint256);
    /// @notice Anyone can read the address authorized to change caps and the fee.
    function owner() external view returns (address);
    /// @notice Only the owner can set caps in USDC base units and TKN base units, respectively.
    function setCaps(uint256 supplyCap, uint256 collateralCap) external;
    /// @notice Only the owner can set the treasury fee in basis points of borrower interest.
    function setFee(uint256 feeBps) external;
}
