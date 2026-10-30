// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {IERC20} from "../interfaces/IERC20.sol";
import {IStrategy} from "../interfaces/IStrategy.sol";

/// @title BaseStrategy
/// @notice Shared bookkeeping for Sluice strategies. A strategy holds assets for exactly one vault,
///         and only that vault may deploy, undeploy, or harvest.
/// @dev Concrete strategies implement the yield-source calls: `_deploy`, `_undeploy`, `_undeployAll`,
///      `totalAssets`, `_withdrawable` and `_isPositionToken`, and may override `_claimRewards`.
abstract contract BaseStrategy is IStrategy {
    /// @inheritdoc IStrategy
    address public immutable vault;
    /// @inheritdoc IStrategy
    address public immutable asset;

    /// @notice The principal the vault has placed in this strategy, including profit and loss
    ///         booked at past harvests. `harvest` measures the next profit or loss against it.
    /// @dev Only booked assets can be undeployed; interest earned since the last harvest stays in the
    ///      market until harvest books it.
    uint256 public deployedAssets;
    /// @notice Timestamp of the last harvest.
    uint256 public lastHarvest;

    event Deployed(uint256 assets);
    event Undeployed(uint256 assets);
    event Harvested(uint256 previousAssets, uint256 currentAssets);
    event RewardsClaimed(address indexed reward, uint256 amount);

    error OnlyVault();
    error ZeroAmount();
    error TransferFailed();
    error InvalidReward();

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
    function maxUndeploy() public view returns (uint256) {
        uint256 withdrawable = _withdrawable();
        return withdrawable < deployedAssets ? withdrawable : deployedAssets;
    }

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
        if (assets > deployedAssets) assets = deployedAssets;
        returned = _undeploy(assets);
        deployedAssets -= returned;
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

    /// @inheritdoc IStrategy
    function claimRewards(address reward) external onlyVault returns (uint256 claimed) {
        if (reward == asset || _isPositionToken(reward)) revert InvalidReward();
        _claimRewards(reward);
        claimed = IERC20(reward).balanceOf(address(this));
        if (claimed > 0 && !IERC20(reward).transfer(vault, claimed)) revert TransferFailed();
        emit RewardsClaimed(reward, claimed);
    }

    function _sendToVault(uint256 assets) private {
        if (assets > 0 && !IERC20(asset).transfer(vault, assets)) revert TransferFailed();
    }

    /// @dev What the yield source would let the strategy withdraw right now.
    function _withdrawable() internal view virtual returns (uint256);

    /// @dev True for the token that represents the strategy's position in its market.
    function _isPositionToken(address token) internal view virtual returns (bool);

    /// @dev Pulls `reward` owed to the strategy into its balance. Rewards a distributor sends to the
    ///      strategy directly need nothing here.
    function _claimRewards(address reward) internal virtual {}

    /// @dev Puts `assets`, already held by the strategy, to work.
    function _deploy(uint256 assets) internal virtual;

    /// @dev Frees up to `assets` into the strategy's balance and returns the amount freed.
    function _undeploy(uint256 assets) internal virtual returns (uint256);

    /// @dev Frees everything into the strategy's balance and returns the amount freed.
    function _undeployAll() internal virtual returns (uint256);
}
