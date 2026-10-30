// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

/// @notice A strategy holds part of a SluiceVault's assets in one yield source.
/// @dev Only the vault that deployed the strategy may move funds through it.
interface IStrategy {
    /// @notice The vault this strategy reports to.
    function vault() external view returns (address);

    /// @notice The token the strategy accepts and returns.
    function asset() external view returns (address);

    /// @notice Assets the strategy holds right now, valued in `asset`.
    function totalAssets() external view returns (uint256);

    /// @notice Assets the strategy can return to the vault in one call.
    function maxUndeploy() external view returns (uint256);

    /// @notice Pulls `assets` from the vault and puts them to work.
    function deploy(uint256 assets) external;

    /// @notice Returns up to `assets` to the vault.
    /// @return returned The assets sent to the vault.
    function undeploy(uint256 assets) external returns (uint256 returned);

    /// @notice Returns everything the strategy holds to the vault.
    /// @return returned The assets sent to the vault.
    function undeployAll() external returns (uint256 returned);

    /// @notice Books what the strategy earned or lost since the last harvest.
    /// @return delta Profit when positive, loss when negative.
    function harvest() external returns (int256 delta);
}
