// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {ERC20} from "../../src/tokens/ERC20.sol";
import {MockERC20} from "./MockERC20.sol";

/// @notice A lending market stand-in: an ERC-4626 pool whose value grows when interest is paid in
///         and whose free liquidity drops when assets are lent out.
contract MockLendingMarket is ERC20 {
    MockERC20 public immutable underlying;
    uint256 public lent;

    constructor(MockERC20 underlying_) ERC20("Market USDC", "mUSDC", underlying_.decimals()) {
        underlying = underlying_;
    }

    function asset() external view returns (address) {
        return address(underlying);
    }

    function totalAssets() public view returns (uint256) {
        return underlying.balanceOf(address(this)) + lent;
    }

    function convertToShares(uint256 assets) public view returns (uint256) {
        return assets * (totalSupply + 1) / (totalAssets() + 1);
    }

    function convertToAssets(uint256 shares) public view returns (uint256) {
        return shares * (totalAssets() + 1) / (totalSupply + 1);
    }

    function previewRedeem(uint256 shares) external view returns (uint256) {
        return convertToAssets(shares);
    }

    function maxWithdraw(address owner) public view returns (uint256) {
        uint256 owned = convertToAssets(balanceOf[owner]);
        uint256 cash = underlying.balanceOf(address(this));
        return owned < cash ? owned : cash;
    }

    function deposit(uint256 assets, address receiver) external returns (uint256 shares) {
        shares = convertToShares(assets);
        underlying.transferFrom(msg.sender, address(this), assets);
        _mint(receiver, shares);
    }

    function withdraw(uint256 assets, address receiver, address owner) external returns (uint256 shares) {
        require(assets <= maxWithdraw(owner), "liquidity");
        uint256 supply = totalSupply;
        shares = assets * (supply + 1) / (totalAssets() + 1);
        if (shares * (totalAssets() + 1) < assets * (supply + 1)) shares += 1;
        if (msg.sender != owner) _spendAllowance(owner, msg.sender, shares);
        _burn(owner, shares);
        underlying.transfer(receiver, assets);
    }

    function redeem(uint256 shares, address receiver, address owner) external returns (uint256 assets) {
        assets = convertToAssets(shares);
        if (msg.sender != owner) _spendAllowance(owner, msg.sender, shares);
        _burn(owner, shares);
        underlying.transfer(receiver, assets);
    }

    /// @notice Borrowers pay `assets` of interest into the pool.
    function accrueInterest(uint256 assets) external {
        underlying.mint(address(this), assets);
    }

    /// @notice Borrowers take `assets` of the pool's cash.
    function borrow(uint256 assets) external {
        lent += assets;
        underlying.transfer(msg.sender, assets);
    }

    /// @notice A borrower defaults and `assets` of lent principal is written off as bad debt.
    function writeOff(uint256 assets) external {
        lent -= assets;
    }

    /// @notice Borrowers pay back `assets` of principal.
    function repay(uint256 assets) external {
        lent -= assets;
        underlying.transferFrom(msg.sender, address(this), assets);
    }
}
