// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {Test} from "forge-std/Test.sol";
import {Market} from "../workspace/src/Market.sol";
import {IMarket} from "../workspace/src/interfaces/IMarket.sol";

contract MarketToken {
    uint8 public immutable decimals;
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    constructor(uint8 decimals_) { decimals = decimals_; }
    function mint(address account, uint256 amount) external { balanceOf[account] += amount; }
    function approve(address spender, uint256 amount) external returns (bool) {
        allowance[msg.sender][spender] = amount;
        return true;
    }
    function transfer(address to, uint256 amount) external returns (bool) {
        balanceOf[msg.sender] -= amount;
        balanceOf[to] += amount;
        return true;
    }
    function transferFrom(address from, address to, uint256 amount) external returns (bool) {
        if (allowance[from][msg.sender] != type(uint256).max) allowance[from][msg.sender] -= amount;
        balanceOf[from] -= amount;
        balanceOf[to] += amount;
        return true;
    }
}

contract MarketFeed {
    uint256 private value = 10e18;
    bool public unavailable;
    function setPrice(uint256 value_) external { value = value_; }
    function setUnavailable(bool unavailable_) external { unavailable = unavailable_; }
    function price() external view returns (uint256) {
        require(!unavailable, "feed unavailable");
        return value;
    }
}

contract TokenLendingMarketTest is Test {
    address constant LENDER = address(0xA11CE);
    address constant OTHER = address(0xB0B);
    address constant BORROWER = address(0xCA11);
    address constant SECOND = address(0xCA12);
    address constant LIQUIDATOR = address(0x11C);
    address constant TREASURY = address(0xFEE);
    IMarket market;
    MarketToken usdc;
    MarketToken tkn;
    MarketFeed feed;

    function setUp() public {
        usdc = new MarketToken(6);
        tkn = new MarketToken(18);
        feed = new MarketFeed();
        market = IMarket(address(new Market(address(usdc), address(tkn), address(feed), TREASURY)));
        vm.startPrank(TREASURY);
        market.setCaps(2_000_000e6, 1_000_000e18);
        market.setFee(1000);
        vm.stopPrank();
        address[7] memory users = [LENDER, OTHER, BORROWER, SECOND, LIQUIDATOR, TREASURY, address(this)];
        for (uint256 i; i < users.length; ++i) {
            usdc.mint(users[i], 10_000_000e6);
            tkn.mint(users[i], 10_000_000e18);
            vm.startPrank(users[i]);
            usdc.approve(address(market), type(uint256).max);
            tkn.approve(address(market), type(uint256).max);
            vm.stopPrank();
        }
    }

    function supply(address who, uint256 amount) private {
        vm.prank(who);
        market.supply(amount, who);
    }

    function collateral(address who, uint256 amount) private {
        vm.prank(who);
        market.supplyCollateral(amount, who);
    }

    function borrow(address who, uint256 amount) private {
        vm.prank(who);
        market.borrow(amount, who);
    }

    function seed() private {
        supply(LENDER, 10_000e6);
        collateral(BORROWER, 2_000e18);
        borrow(BORROWER, 5_000e6);
    }

    function books() private view {
        assertEq(market.totalSupplyAssets() - market.totalBorrowAssets(), usdc.balanceOf(address(market)), "booked net assets equal cash");
    }

    function test_marketWorksAndBooksBalance() public {
        uint256 lenderStart = usdc.balanceOf(LENDER);
        uint256 treasuryStart = usdc.balanceOf(TREASURY);
        supply(LENDER, 10_000e6);
        assertEq(market.supplyBalance(LENDER), 10_000e6, "lender owns supplied principal");
        books();
        collateral(BORROWER, 2_000e18);
        uint256 borrowerStart = usdc.balanceOf(BORROWER);
        borrow(BORROWER, 5_000e6);
        assertEq(usdc.balanceOf(BORROWER) - borrowerStart, 5_000e6, "borrow pays requested USDC");
        assertEq(market.borrowBalance(BORROWER), 5_000e6, "initial debt uses USDC units");
        assertTrue(market.isHealthy(BORROWER), "collateral covers loan at ten-dollar price");
        collateral(SECOND, 100e18);
        vm.prank(SECOND);
        vm.expectRevert();
        market.borrow(805e6, SECOND);
        vm.prank(BORROWER);
        vm.expectRevert();
        market.withdrawCollateral(1_800e18, BORROWER);
        assertEq(market.collateralBalance(BORROWER), 2_000e18, "unsafe withdrawal keeps collateral in place");
        books();
        assertEq(market.owner(), TREASURY, "constructor assigns owner");
        assertEq(market.fee(), 1000, "fee uses basis points");
        vm.expectRevert();
        market.setCaps(1, 1);
        vm.expectRevert();
        market.setFee(0);
        vm.warp(block.timestamp + 30 days);
        uint256 debt = market.borrowBalance(BORROWER);
        assertGt(debt, 5_000e6, "positive interest at half utilization");
        uint256 interest = debt - 5_000e6;
        books();
        vm.prank(BORROWER);
        market.repay(debt, BORROWER);
        assertEq(market.borrowBalance(BORROWER), 0, "full repayment clears debt");
        assertEq(borrowerStart - usdc.balanceOf(BORROWER), interest, "borrower pays principal plus interest");
        books();
        vm.prank(BORROWER);
        market.withdrawCollateral(2_000e18, BORROWER);
        assertEq(market.collateralBalance(BORROWER), 0, "borrower retrieves collateral");
        assertEq(tkn.balanceOf(BORROWER), 10_000_000e18, "all collateral returned");
        uint256 treasuryClaim = market.supplyBalance(TREASURY);
        uint256 treasuryCash = usdc.balanceOf(TREASURY) - treasuryStart;
        assertApproxEqAbs(treasuryClaim + treasuryCash, interest / 10, 5, "treasury gets ten percent of interest");
        uint256 lenderClaim = market.supplyBalance(LENDER);
        assertApproxEqAbs(lenderClaim, 10_000e6 + interest * 9 / 10, 5, "lender gets ninety percent of interest");
        feed.setUnavailable(true);
        vm.prank(LENDER);
        market.withdraw(lenderClaim, LENDER);
        assertEq(usdc.balanceOf(LENDER), lenderStart - 10_000e6 + lenderClaim, "lender receives its full claim without a price");
        books();
        if (treasuryClaim != 0) {
            vm.prank(TREASURY);
            market.withdraw(treasuryClaim, TREASURY);
        }
        assertApproxEqAbs(usdc.balanceOf(TREASURY) - treasuryStart, interest / 10, 5, "treasury can take its fee");
        books();
    }

    function test_interestChargedBeforeTheAction() public {
        seed();
        collateral(SECOND, 2_000e18);
        uint256 initialDebt = market.borrowBalance(BORROWER);
        vm.warp(block.timestamp + 30 days);
        uint256 pendingDebt = market.borrowBalance(BORROWER);
        assertGt(pendingDebt, initialDebt, "view includes idle interest");
        uint256 snapshot = vm.snapshot();
        supply(OTHER, 1);
        uint256 settledDebt = market.borrowBalance(BORROWER);
        assertApproxEqAbs(settledDebt, pendingDebt, 3, "view matches accrued debt");
        assertTrue(vm.revertTo(snapshot), "restore identical idle interval");
        snapshot = vm.snapshot();
        borrow(SECOND, 4_000e6);
        assertApproxEqAbs(market.borrowBalance(BORROWER), settledDebt, 3, "new utilization cannot reprice old interest");
        assertEq(usdc.balanceOf(SECOND), 10_004_000e6, "new borrower receives funds");
        assertTrue(vm.revertTo(snapshot), "restore before repayment");
        vm.prank(BORROWER);
        market.repay(initialDebt, BORROWER);
        assertApproxEqAbs(market.borrowBalance(BORROWER), pendingDebt - initialDebt, 3, "repayment leaves accrued interest owed");
        assertEq(usdc.balanceOf(BORROWER), 10_000_000e6, "repayment transfers initial principal");
    }

    function test_strayTokensChangeNothing() public {
        seed();
        uint256 supplyBefore = market.supplyBalance(LENDER);
        uint256 debtBefore = market.borrowBalance(BORROWER);
        uint256 totalBefore = market.totalSupplyAssets();
        uint256 borrowBefore = market.totalBorrowAssets();
        usdc.transfer(address(market), 3_000_000e6);
        tkn.transfer(address(market), 2_000_000e18);
        assertEq(market.supplyBalance(LENDER), supplyBefore, "USDC donation creates no lender assets");
        assertEq(market.borrowBalance(BORROWER), debtBefore, "donation changes no debt");
        assertEq(market.collateralBalance(BORROWER), 2_000e18, "TKN donation creates no collateral");
        assertEq(market.supplyBalance(address(this)), 0, "donor gets no supply claim");
        assertEq(market.collateralBalance(address(this)), 0, "donor gets no collateral claim");
        assertEq(market.totalSupplyAssets(), totalBefore, "supply total ignores donation");
        assertEq(market.totalBorrowAssets(), borrowBefore, "borrow total ignores donation");
        vm.prank(TREASURY);
        market.setCaps(totalBefore + 100e6, 2_010e18);
        assertEq(market.supplyCap(), totalBefore + 100e6, "owner sets supply cap");
        assertEq(market.collateralCap(), 2_010e18, "owner sets collateral cap");
        supply(OTHER, 100e6);
        collateral(SECOND, 10e18);
        assertEq(market.supplyBalance(OTHER), 100e6, "booked room stays usable after donation");
        assertEq(market.collateralBalance(SECOND), 10e18, "collateral room stays usable after donation");
        vm.expectRevert();
        market.supply(1, address(this));
        vm.expectRevert();
        market.supplyCollateral(1, address(this));
    }

    function test_roundingFavoursMarket() public {
        seed();
        collateral(SECOND, 100e18);
        borrow(SECOND, 100e6);
        vm.warp(block.timestamp + 30 days);
        supply(LENDER, 1);
        uint256 lenderStart = usdc.balanceOf(OTHER);
        uint256 debtBefore = market.borrowBalance(SECOND);
        uint256 borrowerStart = usdc.balanceOf(SECOND);
        for (uint256 i; i < 1000; ++i) {
            uint256 oddAmount = 101 + i * 2;
            supply(OTHER, oddAmount);
            uint256 claim = market.supplyBalance(OTHER);
            if (claim != 0) {
                vm.prank(OTHER);
                market.withdraw(claim, OTHER);
            }
            borrow(SECOND, oddAmount);
            vm.prank(SECOND);
            market.repay(oddAmount, SECOND);
        }
        assertLe(usdc.balanceOf(OTHER) + market.supplyBalance(OTHER), lenderStart, "supply cycles cannot mint user value");
        assertEq(usdc.balanceOf(SECOND), borrowerStart, "borrow cycles return every borrowed token");
        assertGe(market.borrowBalance(SECOND), debtBefore, "borrow cycles cannot erase existing debt");
        assertGt(market.borrowBalance(BORROWER), 5_000e6, "interest changed the conversion ratio");
        address tiny = address(0xD057);
        feed.setPrice(1e18);
        vm.prank(address(this));
        market.supplyCollateral(3e12, tiny);
        borrow(tiny, 1);
        assertEq(usdc.balanceOf(tiny), 1, "tiny borrow transfers one USDC base unit");
        uint256 tinyDebt = market.borrowBalance(tiny);
        assertGe(tinyDebt, 1, "tiny debt cannot disappear");
        feed.setPrice(0.5e18);
        assertFalse(market.isHealthy(tiny), "tiny debt still needs collateral value");
        uint256 liquidatorStart = tkn.balanceOf(LIQUIDATOR);
        vm.prank(LIQUIDATOR);
        uint256 seized = market.liquidate(tiny, 100);
        assertGt(seized, 0, "tiny unhealthy loan can be liquidated");
        assertEq(tkn.balanceOf(LIQUIDATOR) - liquidatorStart, seized, "tiny liquidation pays reported collateral");
        assertLt(market.borrowBalance(tiny), tinyDebt, "tiny liquidation reduces debt");
    }

    function test_liquidationFinishes() public {
        seed();
        uint256 debt = market.borrowBalance(BORROWER);
        uint256 insidePrice = debt * 1e30 * 1000 / (2_000e18 * 799);
        feed.setPrice(insidePrice);
        assertTrue(market.isHealthy(BORROWER), "loan at about 79.9 percent is healthy");
        vm.prank(LIQUIDATOR);
        vm.expectRevert();
        market.liquidate(BORROWER, 1_000e6);
        uint256 outsidePrice = debt * 1e30 * 1000 / (2_000e18 * 805);
        feed.setPrice(outsidePrice);
        assertFalse(market.isHealthy(BORROWER), "loan at about 80.5 percent is unhealthy");
        uint256 snapshot = vm.snapshot();
        uint256 liquidatorCash = usdc.balanceOf(LIQUIDATOR);
        uint256 liquidatorTokens = tkn.balanceOf(LIQUIDATOR);
        vm.prank(LIQUIDATOR);
        uint256 seized = market.liquidate(BORROWER, 1_000e6);
        assertEq(liquidatorCash - usdc.balanceOf(LIQUIDATOR), 1_000e6, "liquidator pays requested partial amount");
        assertApproxEqAbs(seized * outsidePrice / 1e30, 1_050e6, 2, "liquidator gets five percent incentive");
        assertEq(tkn.balanceOf(LIQUIDATOR) - liquidatorTokens, seized, "liquidator receives reported TKN");
        assertApproxEqAbs(market.borrowBalance(BORROWER), debt - 1_000e6, 2, "partial liquidation reduces debt");
        assertTrue(vm.revertTo(snapshot), "restore unhealthy loan");
        snapshot = vm.snapshot();
        vm.prank(LIQUIDATOR);
        seized = market.liquidate(BORROWER, debt + 1_000e6);
        assertEq(liquidatorCash - usdc.balanceOf(LIQUIDATOR), debt, "excess request charges only outstanding debt");
        assertEq(market.borrowBalance(BORROWER), 0, "excess request clears debt");
        assertApproxEqAbs(seized * outsidePrice / 1e30, debt * 105 / 100, 2, "full liquidation preserves incentive");
        assertTrue(vm.revertTo(snapshot), "restore distressed borrower");
        feed.setPrice(1e18);
        uint256 cashBefore = usdc.balanceOf(BORROWER);
        vm.prank(BORROWER);
        market.repay(1e6, BORROWER);
        collateral(BORROWER, 1e18);
        assertEq(cashBefore - usdc.balanceOf(BORROWER), 1e6, "distressed borrower can repay");
        assertApproxEqAbs(market.borrowBalance(BORROWER), debt - 1e6, 2, "distressed repayment reduces debt");
        assertEq(market.collateralBalance(BORROWER), 2_001e18, "distressed borrower can add collateral");
        assertFalse(market.isHealthy(BORROWER), "repair actions need not restore health immediately");
    }

    function test_badDebtWrittenOffAgainstLenders() public {
        supply(LENDER, 5_000e6);
        supply(OTHER, 5_000e6);
        collateral(BORROWER, 1_000e18);
        borrow(BORROWER, 5_000e6);
        assertEq(market.supplyBalance(LENDER), 5_000e6, "first lender starts with equal claim");
        assertEq(market.supplyBalance(OTHER), 5_000e6, "second lender starts with equal claim");
        feed.setPrice(1e18);
        uint256 liquidatorCash = usdc.balanceOf(LIQUIDATOR);
        uint256 liquidatorTokens = tkn.balanceOf(LIQUIDATOR);
        vm.prank(LIQUIDATOR);
        uint256 seized = market.liquidate(BORROWER, 100_000e6);
        uint256 paid = liquidatorCash - usdc.balanceOf(LIQUIDATOR);
        assertGt(paid, 0, "liquidator repays covered debt");
        assertApproxEqAbs(paid, uint256(1_000e6) * 100 / 105, 2, "repayment fits collateral and incentive");
        assertEq(seized, 1_000e18, "liquidator takes exhausted collateral");
        assertEq(tkn.balanceOf(LIQUIDATOR) - liquidatorTokens, seized, "all seized TKN reaches liquidator");
        assertEq(market.collateralBalance(BORROWER), 0, "collateral is exhausted");
        assertEq(market.borrowBalance(BORROWER), 0, "uncovered debt leaves borrower");
        assertEq(market.totalBorrowAssets(), 0, "uncovered debt leaves borrow total");
        assertEq(market.totalSupplyAssets(), 5_000e6 + paid, "loss reduces supply total");
        books();
        uint256 firstClaim = market.supplyBalance(LENDER);
        uint256 secondClaim = market.supplyBalance(OTHER);
        assertApproxEqAbs(firstClaim, (5_000e6 + paid) / 2, 1, "first lender takes half the loss");
        assertEq(firstClaim, secondClaim, "equal lenders share loss equally");
        uint256 firstCash = usdc.balanceOf(LENDER);
        uint256 secondCash = usdc.balanceOf(OTHER);
        vm.prank(LENDER);
        market.withdraw(firstClaim, LENDER);
        vm.prank(OTHER);
        market.withdraw(secondClaim, OTHER);
        assertEq(usdc.balanceOf(LENDER) - firstCash, firstClaim, "first lender receives full reduced claim");
        assertEq(usdc.balanceOf(OTHER) - secondCash, firstClaim, "last lender receives equal payment");
        books();
    }
}
