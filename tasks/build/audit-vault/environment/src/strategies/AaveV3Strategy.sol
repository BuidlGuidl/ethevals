// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {IERC20} from "../interfaces/IERC20.sol";
import {IAavePool, IAToken, IRewardsController} from "../interfaces/IAavePool.sol";
import {BaseStrategy} from "./BaseStrategy.sol";

/// @title AaveV3Strategy
/// @notice Supplies a vault's assets to one Aave v3 reserve and earns its supply rate.
/// @dev The strategy holds aTokens, whose balance grows as interest accrues. The reserve's free cash
///      is the underlying held by the aToken contract.
contract AaveV3Strategy is BaseStrategy {
    /// @dev Bits of the reserve configuration that mark it active, frozen and paused (Aave v3 layout).
    uint256 private constant ACTIVE_BIT = 56;
    uint256 private constant FROZEN_BIT = 57;
    uint256 private constant PAUSED_BIT = 60;

    /// @notice The Aave v3 pool this strategy supplies.
    IAavePool public immutable pool;
    /// @notice The aToken the pool mints for `asset`.
    IAToken public immutable aToken;
    /// @notice The Aave incentives controller that pays rewards on the aToken.
    IRewardsController public immutable rewardsController;

    error ReserveUnavailable();

    constructor(address vault_, IAToken aToken_, IRewardsController rewardsController_)
        BaseStrategy(vault_, aToken_.UNDERLYING_ASSET_ADDRESS())
    {
        aToken = aToken_;
        rewardsController = rewardsController_;
        pool = IAavePool(aToken_.POOL());
        if (!IERC20(asset).approve(address(pool), type(uint256).max)) revert TransferFailed();
    }

    /// @notice The aToken balance, which already includes accrued interest.
    function totalAssets() public view override returns (uint256) {
        return aToken.balanceOf(address(this));
    }

    /// @dev Limited by the reserve's free cash as well as the strategy's position. Zero while the
    ///      reserve is paused.
    function _withdrawable() internal view override returns (uint256) {
        uint256 config = pool.getConfiguration(asset).data;
        if (!_flag(config, ACTIVE_BIT) || _flag(config, PAUSED_BIT)) return 0;
        uint256 position = aToken.balanceOf(address(this));
        uint256 cash = IERC20(asset).balanceOf(address(aToken));
        return position < cash ? position : cash;
    }

    function _isPositionToken(address token) internal view override returns (bool) {
        return token == address(aToken);
    }

    function _claimRewards(address reward) internal override {
        address[] memory assets = new address[](1);
        assets[0] = address(aToken);
        rewardsController.claimRewards(assets, type(uint256).max, address(this), reward);
    }

    function _deploy(uint256 assets) internal override {
        uint256 config = pool.getConfiguration(asset).data;
        if (!_flag(config, ACTIVE_BIT) || _flag(config, FROZEN_BIT) || _flag(config, PAUSED_BIT)) {
            revert ReserveUnavailable();
        }
        pool.supply(asset, assets, address(this), 0);
    }

    function _undeploy(uint256 assets) internal override returns (uint256) {
        uint256 available = _withdrawable();
        if (assets > available) assets = available;
        if (assets == 0) return 0;
        return pool.withdraw(asset, assets, address(this));
    }

    function _undeployAll() internal override returns (uint256) {
        if (aToken.balanceOf(address(this)) == 0) return 0;
        return pool.withdraw(asset, type(uint256).max, address(this));
    }

    function _flag(uint256 config, uint256 bit) private pure returns (bool) {
        return (config >> bit) & 1 == 1;
    }
}
