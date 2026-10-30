// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {IERC20} from "../interfaces/IERC20.sol";
import {IStrategy} from "../interfaces/IStrategy.sol";

/// @title BaseStrategy
/// @notice Shared bookkeeping for Sluice strategies. A strategy holds assets for exactly one vault,
///         and only that vault may deploy, undeploy, or harvest.
/// @dev Concrete strategies implement the yield-source calls: `_deploy`, `_undeploy`, `_undeployAll`,
///      `totalAssets`, and `maxUndeploy`.
abstract contract BaseStrategy is IStrategy {
    /// @inheritdoc IStrategy
    address public immutable vault;
    /// @inheritdoc IStrategy
    address public immutable asset;

    /// @notice The principal the vault has placed in this strategy, including profit and loss
    ///         booked at past harvests. `harvest` measures the next profit or loss against it.
    uint256 public deployedAssets;
    /// @notice Timestamp of the last harvest.
    uint256 public lastHarvest;

    event Deployed(uint256 assets);
    event Undeployed(uint256 assets);
    event Harvested(uint256 previousAssets, uint256 currentAssets);

    error OnlyVault();
    error ZeroAmount();
    error TransferFailed();

    modifier onlyVault() {
        if (msg.sender != vault) revert OnlyVault();
        _;
    }

    constructor(address vault_, address asset_) {
        vault = vault_;
        asset = asset_;
    }

    /// @inheritdoc IStrategy
    function totalAssets() public view virtual returns (uint256);

    /// @inheritdoc IStrategy
    function maxUndeploy() public view virtual returns (uint256);

    /// @inheritdoc IStrategy
    function deploy(uint256 assets) external onlyVault {
        if (assets == 0) revert ZeroAmount();
        if (!IERC20(asset).transferFrom(vault, address(this), assets)) revert TransferFailed();
        _deploy(assets);
        deployedAssets += assets;
        emit Deployed(assets);
    }

    /// @inheritdoc IStrategy
    function undeploy(uint256 assets) external onlyVault returns (uint256 returned) {
        if (assets == 0) revert ZeroAmount();
        returned = _undeploy(assets);
        _sendToVault(returned);
        emit Undeployed(returned);
    }

    /// @inheritdoc IStrategy
    function undeployAll() external onlyVault returns (uint256 returned) {
        returned = _undeployAll();
        deployedAssets = 0;
        _sendToVault(returned);
        emit Undeployed(returned);
    }

    /// @inheritdoc IStrategy
    function harvest() external onlyVault returns (int256 delta) {
        uint256 previous = deployedAssets;
        uint256 current = totalAssets();
        delta = int256(current) - int256(previous);
        deployedAssets = current;
        lastHarvest = block.timestamp;
        emit Harvested(previous, current);
    }

    function _sendToVault(uint256 assets) private {
        if (assets > 0 && !IERC20(asset).transfer(vault, assets)) revert TransferFailed();
    }

    /// @dev Puts `assets`, already held by the strategy, to work.
    function _deploy(uint256 assets) internal virtual;

    /// @dev Frees up to `assets` into the strategy's balance and returns the amount freed.
    function _undeploy(uint256 assets) internal virtual returns (uint256);

    /// @dev Frees everything into the strategy's balance and returns the amount freed.
    function _undeployAll() internal virtual returns (uint256);
}
