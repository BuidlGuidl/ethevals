// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {MockERC20} from "./MockERC20.sol";

/// @notice An Aave RewardsController stand-in: pays whatever reward was set for the caller.
contract MockRewardsController {
    mapping(address => mapping(address => uint256)) public owed;

    function setOwed(address account, address reward, uint256 amount) external {
        owed[account][reward] = amount;
    }

    function claimRewards(address[] calldata, uint256, address to, address reward) external returns (uint256 amount) {
        amount = owed[msg.sender][reward];
        owed[msg.sender][reward] = 0;
        MockERC20(reward).mint(to, amount);
    }
}

/// @notice A swap router stand-in that sells any token at a fixed price in `tokenOut` units.
contract MockSwapper {
    /// @notice tokenOut paid per 1e18 of tokenIn.
    uint256 public price;

    constructor(uint256 price_) {
        price = price_;
    }

    function swap(address tokenIn, address tokenOut, uint256 amountIn, uint256 minAmountOut, address receiver)
        external
        returns (uint256 amountOut)
    {
        MockERC20(tokenIn).transferFrom(msg.sender, address(this), amountIn);
        amountOut = amountIn * price / 1e18;
        require(amountOut >= minAmountOut, "slippage");
        MockERC20(tokenOut).mint(receiver, amountOut);
    }
}
