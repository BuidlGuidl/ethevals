// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {IERC20} from "../interfaces/IERC20.sol";
import {IERC4626} from "../interfaces/IERC4626.sol";
import {BaseStrategy} from "./BaseStrategy.sol";

/// @title LendingMarketStrategy
/// @notice Supplies a vault's assets to one ERC-4626 lending market and earns the market's supply rate.
contract LendingMarketStrategy is BaseStrategy {
    /// @notice The lending market this strategy supplies.
    IERC4626 public immutable market;

    constructor(address vault_, IERC4626 market_) BaseStrategy(vault_, market_.asset()) {
        market = market_;
        if (!IERC20(asset).approve(address(market_), type(uint256).max)) revert TransferFailed();
    }

    /// @notice The market shares held, valued at what redeeming them would return.
    function totalAssets() public view override returns (uint256) {
        return market.previewRedeem(market.balanceOf(address(this)));
    }

    /// @dev Limited by the market's free liquidity as well as the strategy's position.
    function _withdrawable() internal view override returns (uint256) {
        return market.maxWithdraw(address(this));
    }

    function _isPositionToken(address token) internal view override returns (bool) {
        return token == address(market);
    }

    function _deploy(uint256 assets) internal override {
        market.deposit(assets, address(this));
    }

    function _undeploy(uint256 assets) internal override returns (uint256) {
        uint256 available = market.maxWithdraw(address(this));
        if (assets > available) assets = available;
        if (assets == 0) return 0;
        market.withdraw(assets, address(this), address(this));
        return assets;
    }

    function _undeployAll() internal override returns (uint256) {
        uint256 shares = market.balanceOf(address(this));
        if (shares == 0) return 0;
        return market.redeem(shares, address(this), address(this));
    }
}
