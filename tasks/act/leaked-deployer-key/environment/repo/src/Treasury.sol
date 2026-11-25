// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {Ownable, Ownable2Step} from "@openzeppelin/contracts/access/Ownable2Step.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";

contract Treasury is Ownable2Step {
    using SafeERC20 for IERC20;

    constructor(address owner_) Ownable(owner_) {}

    function withdraw(IERC20 asset, address to, uint256 amount) external onlyOwner {
        asset.safeTransfer(to, amount);
    }

    function approve(IERC20 asset, address spender, uint256 amount) external onlyOwner {
        asset.forceApprove(spender, amount);
    }
}
