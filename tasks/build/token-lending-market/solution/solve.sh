#!/bin/sh
set -eu
mkdir -p /workspace/src
cat > /workspace/src/Market.sol <<'SOL'
// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {IMarket} from "./interfaces/IMarket.sol";
import {IPriceFeed} from "./interfaces/IPriceFeed.sol";

contract Market is IMarket {
    address public immutable usdc;
    address public immutable tkn;
    IPriceFeed public immutable priceFeed;
    address public immutable owner;
    uint256 public supplyCap = 2_000_000e6;
    uint256 public collateralCap = 1_000_000e18;
    uint256 public fee = 1000;
    uint256 private supplied;
    uint256 private borrowed;
    uint256 private supplyShares;
    uint256 private borrowShares;
    uint256 private collateralTotal;
    uint256 private lastAccrual;
    bool private entered;
    mapping(address => uint256) private lenderShares;
    mapping(address => uint256) private debtorShares;
    mapping(address => uint256) public collateralBalance;

    event Supplied(address indexed payer, address indexed account, uint256 assets);
    event Withdrawn(address indexed account, address indexed to, uint256 assets);
    event CollateralSupplied(address indexed payer, address indexed account, uint256 assets);
    event CollateralWithdrawn(address indexed account, address indexed to, uint256 assets);
    event Borrowed(address indexed account, address indexed to, uint256 assets);
    event Repaid(address indexed payer, address indexed account, uint256 assets);
    event Liquidated(address indexed account, address indexed liquidator, uint256 paid, uint256 seized, uint256 loss);
    event CapsSet(uint256 supplyCap, uint256 collateralCap);
    event FeeSet(uint256 fee);

    constructor(address usdc_, address tkn_, address priceFeed_, address owner_) {
        require(usdc_ != address(0) && tkn_ != address(0) && priceFeed_ != address(0) && owner_ != address(0), "address");
        usdc = usdc_;
        tkn = tkn_;
        priceFeed = IPriceFeed(priceFeed_);
        owner = owner_;
        lastAccrual = block.timestamp;
    }

    modifier action() {
        require(!entered, "reentry");
        entered = true;
        accrue();
        _;
        entered = false;
    }

    function up(uint256 x, uint256 y) private pure returns (uint256) {
        return x == 0 ? 0 : (x - 1) / y + 1;
    }

    function preview() private view returns (uint256 s, uint256 b, uint256 feeShares) {
        s = supplied;
        b = borrowed;
        if (b == 0 || block.timestamp == lastAccrual) return (s, b, 0);
        uint256 utilization = b * 1e18 / s;
        uint256 annualRate = 2e16 + utilization * 18 / 100;
        uint256 interest = b * annualRate * (block.timestamp - lastAccrual) / 1e18 / 365 days;
        s += interest;
        b += interest;
        uint256 feeAssets = interest * fee / 10_000;
        feeShares = feeAssets * supplyShares / (s - feeAssets);
    }

    function accrue() private {
        uint256 feeShares;
        (supplied, borrowed, feeShares) = preview();
        supplyShares += feeShares;
        lenderShares[owner] += feeShares;
        lastAccrual = block.timestamp;
    }

    function totalSupplyAssets() external view returns (uint256) {
        (uint256 s,,) = preview();
        return s;
    }

    function totalBorrowAssets() external view returns (uint256) {
        (,uint256 b,) = preview();
        return b;
    }

    function borrowBalance(address account) public view returns (uint256) {
        (,uint256 b,) = preview();
        return borrowShares == 0 ? 0 : up(debtorShares[account] * b, borrowShares);
    }

    function supplyBalance(address account) external view returns (uint256) {
        (uint256 s,,uint256 fs) = preview();
        uint256 shares = lenderShares[account] + (account == owner ? fs : 0);
        return supplyShares + fs == 0 ? 0 : shares * s / (supplyShares + fs);
    }

    function isHealthy(address account) public view returns (bool) {
        uint256 debt = borrowBalance(account);
        if (debt == 0) return true;
        uint256 value = collateralBalance[account] * priceFeed.price() / 1e30;
        return debt <= value * 80 / 100;
    }

    function tokenCall(address token, bytes memory data) private {
        (bool ok, bytes memory result) = token.call(data);
        require(ok && (result.length == 0 || abi.decode(result, (bool))), "token transfer");
    }

    function pull(address token, uint256 assets) private {
        tokenCall(token, abi.encodeWithSignature("transferFrom(address,address,uint256)", msg.sender, address(this), assets));
    }

    function push(address token, address to, uint256 assets) private {
        require(to != address(0), "recipient");
        tokenCall(token, abi.encodeWithSignature("transfer(address,uint256)", to, assets));
    }

    function supply(uint256 assets, address onBehalf) external action {
        require(assets != 0 && onBehalf != address(0), "supply");
        require(supplied + assets <= supplyCap, "supply cap");
        uint256 shares = supplyShares == 0 ? assets * 1e6 : assets * supplyShares / supplied;
        require(shares != 0, "supply dust");
        lenderShares[onBehalf] += shares;
        supplyShares += shares;
        supplied += assets;
        pull(usdc, assets);
        emit Supplied(msg.sender, onBehalf, assets);
    }

    function withdraw(uint256 assets, address to) external action {
        require(assets != 0 && assets <= supplied - borrowed, "liquidity");
        uint256 shares = up(assets * supplyShares, supplied);
        lenderShares[msg.sender] -= shares;
        supplyShares -= shares;
        supplied -= assets;
        push(usdc, to, assets);
        emit Withdrawn(msg.sender, to, assets);
    }

    function supplyCollateral(uint256 assets, address onBehalf) external action {
        require(assets != 0 && onBehalf != address(0), "collateral");
        require(collateralTotal + assets <= collateralCap, "collateral cap");
        collateralBalance[onBehalf] += assets;
        collateralTotal += assets;
        pull(tkn, assets);
        emit CollateralSupplied(msg.sender, onBehalf, assets);
    }

    function withdrawCollateral(uint256 assets, address to) external action {
        collateralBalance[msg.sender] -= assets;
        collateralTotal -= assets;
        require(isHealthy(msg.sender), "health");
        push(tkn, to, assets);
        emit CollateralWithdrawn(msg.sender, to, assets);
    }

    function borrow(uint256 assets, address to) external action {
        require(assets != 0 && assets <= supplied - borrowed, "liquidity");
        uint256 shares = borrowShares == 0 ? assets * 1e6 : up(assets * borrowShares, borrowed);
        debtorShares[msg.sender] += shares;
        borrowShares += shares;
        borrowed += assets;
        require(isHealthy(msg.sender), "health");
        push(usdc, to, assets);
        emit Borrowed(msg.sender, to, assets);
    }

    function repayDebt(address account, uint256 assets) private returns (uint256 paid) {
        uint256 debt = borrowShares == 0 ? 0 : up(debtorShares[account] * borrowed, borrowShares);
        paid = assets < debt ? assets : debt;
        uint256 shares = paid == debt ? debtorShares[account] : paid * borrowShares / borrowed;
        require(paid != 0 && shares != 0, "repay dust");
        debtorShares[account] -= shares;
        borrowShares -= shares;
        borrowed -= paid;
    }

    function repay(uint256 assets, address onBehalf) external action {
        uint256 paid = repayDebt(onBehalf, assets);
        pull(usdc, paid);
        emit Repaid(msg.sender, onBehalf, paid);
    }

    function liquidate(address borrower, uint256 repayAssets) external action returns (uint256 seizedCollateral) {
        require(!isHealthy(borrower), "healthy");
        uint256 price = priceFeed.price();
        require(price != 0, "price");
        uint256 collateral = collateralBalance[borrower];
        uint256 covered = collateral * price * 100 / (1e30 * 105);
        uint256 paid = repayDebt(borrower, repayAssets < covered ? repayAssets : covered);
        seizedCollateral = paid == covered ? collateral : paid * 105 * 1e30 / (100 * price);
        if (seizedCollateral > collateral) seizedCollateral = collateral;
        collateralBalance[borrower] -= seizedCollateral;
        collateralTotal -= seizedCollateral;
        uint256 loss;
        if (collateralBalance[borrower] == 0 && debtorShares[borrower] != 0) {
            loss = up(debtorShares[borrower] * borrowed, borrowShares);
            borrowShares -= debtorShares[borrower];
            debtorShares[borrower] = 0;
            borrowed -= loss;
            supplied -= loss;
        }
        pull(usdc, paid);
        push(tkn, msg.sender, seizedCollateral);
        emit Liquidated(borrower, msg.sender, paid, seizedCollateral, loss);
    }

    function setCaps(uint256 supplyCap_, uint256 collateralCap_) external action {
        require(msg.sender == owner, "owner");
        supplyCap = supplyCap_;
        collateralCap = collateralCap_;
        emit CapsSet(supplyCap_, collateralCap_);
    }

    function setFee(uint256 feeBps) external action {
        require(msg.sender == owner && feeBps <= 10_000, "fee owner");
        fee = feeBps;
        emit FeeSet(feeBps);
    }
}
SOL
