// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

/// @notice The subset of the Aave v3 Pool that Sluice strategies call.
interface IAavePool {
    struct ReserveConfigurationMap {
        uint256 data;
    }

    function supply(address asset, uint256 amount, address onBehalfOf, uint16 referralCode) external;
    function withdraw(address asset, uint256 amount, address to) external returns (uint256);
    function getConfiguration(address asset) external view returns (ReserveConfigurationMap memory);
}

/// @notice The subset of an Aave v3 aToken that Sluice strategies read. Balances grow as interest accrues.
interface IAToken {
    function balanceOf(address account) external view returns (uint256);
    function UNDERLYING_ASSET_ADDRESS() external view returns (address);
    function POOL() external view returns (address);
}
