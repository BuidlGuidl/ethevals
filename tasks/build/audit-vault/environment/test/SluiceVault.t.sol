// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {Test} from "forge-std/Test.sol";
import {SluiceVault} from "../src/SluiceVault.sol";
import {LendingMarketStrategy} from "../src/strategies/LendingMarketStrategy.sol";
import {IStrategy} from "../src/interfaces/IStrategy.sol";
import {IERC4626} from "../src/interfaces/IERC4626.sol";
import {MockERC20} from "./mocks/MockERC20.sol";
import {MockLendingMarket} from "./mocks/MockLendingMarket.sol";

contract SluiceVaultTest is Test {
    address internal owner = makeAddr("owner");
    address internal keeper = makeAddr("keeper");
    address internal treasury = makeAddr("treasury");
    address internal alice = makeAddr("alice");
    address internal bob = makeAddr("bob");

    MockERC20 internal usdc;
    MockLendingMarket internal marketA;
    MockLendingMarket internal marketB;
    SluiceVault internal vault;
    LendingMarketStrategy internal strategyA;
    LendingMarketStrategy internal strategyB;

    function setUp() public {
        usdc = new MockERC20("USD Coin", "USDC", 6);
        marketA = new MockLendingMarket(usdc);
        marketB = new MockLendingMarket(usdc);
        vault = new SluiceVault(usdc, "Sluice USDC", "slUSDC", owner, keeper, treasury, 1_500);
        strategyA = new LendingMarketStrategy(address(vault), IERC4626(address(marketA)));
        strategyB = new LendingMarketStrategy(address(vault), IERC4626(address(marketB)));

        vm.startPrank(owner);
        vault.addStrategy(strategyA, 1_000_000e6);
        vault.addStrategy(strategyB, 1_000_000e6);
        vm.stopPrank();

        _fund(alice, 1_000_000e6);
        _fund(bob, 1_000_000e6);
    }

    function _fund(address account, uint256 amount) internal {
        usdc.mint(account, amount);
        vm.prank(account);
        usdc.approve(address(vault), type(uint256).max);
    }

    function _deposit(address account, uint256 amount) internal returns (uint256) {
        vm.prank(account);
        return vault.deposit(amount, account);
    }

    function test_metadata() public view {
        assertEq(vault.asset(), address(usdc));
        assertEq(vault.decimals(), 12);
        assertEq(vault.withdrawQueueLength(), 2);
    }

    function test_depositAndRedeemRoundTrip() public {
        uint256 shares = _deposit(alice, 100_000e6);
        assertEq(vault.balanceOf(alice), shares);
        assertEq(vault.totalAssets(), 100_000e6);

        vm.prank(alice);
        uint256 assets = vault.redeem(shares, alice, alice);
        assertEq(assets, 100_000e6);
        assertEq(usdc.balanceOf(alice), 1_000_000e6);
    }

    function test_allocateMovesIdleIntoStrategy() public {
        _deposit(alice, 500_000e6);
        vm.prank(keeper);
        vault.allocate(strategyA, 300_000e6);

        assertEq(usdc.balanceOf(address(vault)), 200_000e6);
        assertEq(strategyA.totalAssets(), 300_000e6);
        assertEq(strategyA.deployedAssets(), 300_000e6);
        assertEq(vault.totalAssets(), 500_000e6);
    }

    function test_allocateRespectsCap() public {
        _deposit(alice, 1_000_000e6);
        _deposit(bob, 500_000e6);
        vm.prank(keeper);
        vm.expectRevert(SluiceVault.ExceedsCap.selector);
        vault.allocate(strategyA, 1_000_001e6);
    }

    function test_onlyKeeperAllocates() public {
        _deposit(alice, 100_000e6);
        vm.prank(alice);
        vm.expectRevert(SluiceVault.Unauthorized.selector);
        vault.allocate(strategyA, 1e6);
    }

    function test_onlyVaultMovesStrategyFunds() public {
        vm.expectRevert();
        strategyA.undeploy(1e6);
        vm.expectRevert();
        strategyA.harvest();
    }

    function test_harvestChargesPerformanceFee() public {
        _deposit(alice, 1_000_000e6);
        vm.prank(keeper);
        vault.allocate(strategyA, 1_000_000e6);

        marketA.accrueInterest(40_000e6);
        vm.prank(keeper);
        vault.harvest(strategyA);

        assertApproxEqAbs(vault.accruedFees(), 6_000e6, 1);
        assertApproxEqAbs(strategyA.deployedAssets(), 1_040_000e6, 1);
    }

    function test_harvestBooksLossWithoutFee() public {
        _deposit(alice, 1_000_000e6);
        vm.prank(keeper);
        vault.allocate(strategyA, 500_000e6);

        vm.prank(address(marketA));
        usdc.transfer(address(0xdead), 10_000e6);
        vm.prank(keeper);
        vault.harvest(strategyA);

        assertEq(vault.accruedFees(), 0);
        assertEq(strategyA.deployedAssets(), 490_000e6);
    }

    function test_withdrawPullsFromStrategiesInQueueOrder() public {
        _deposit(alice, 600_000e6);
        vm.startPrank(keeper);
        vault.allocate(strategyA, 300_000e6);
        vault.allocate(strategyB, 300_000e6);
        vm.stopPrank();

        vm.prank(alice);
        vault.withdraw(400_000e6, alice, alice);

        assertEq(strategyA.totalAssets(), 0);
        assertEq(strategyB.totalAssets(), 200_000e6);
        assertEq(usdc.balanceOf(alice), 800_000e6);
    }

    function test_withdrawLimitedByMarketLiquidity() public {
        _deposit(alice, 100_000e6);
        vm.prank(keeper);
        vault.allocate(strategyA, 100_000e6);
        marketA.borrow(90_000e6);

        assertEq(vault.maxWithdraw(alice), 10_000e6);
        vm.prank(alice);
        vm.expectRevert(SluiceVault.ExceedsMaxWithdraw.selector);
        vault.withdraw(10_000e6 + 1, alice, alice);
    }

    function test_removeStrategyReturnsEverything() public {
        _deposit(alice, 500_000e6);
        vm.prank(keeper);
        vault.allocate(strategyB, 500_000e6);

        vm.prank(owner);
        vault.removeStrategy(strategyB);

        assertEq(vault.withdrawQueueLength(), 1);
        assertEq(usdc.balanceOf(address(vault)), 500_000e6);
        assertEq(strategyB.deployedAssets(), 0);
        (bool active,) = vault.strategies(strategyB);
        assertFalse(active);
    }

    function test_depositLimitAndPause() public {
        vm.prank(owner);
        vault.setDepositLimit(150_000e6);
        _deposit(alice, 100_000e6);
        assertEq(vault.maxDeposit(bob), 50_000e6);

        vm.prank(bob);
        vm.expectRevert(SluiceVault.ExceedsMaxDeposit.selector);
        vault.deposit(50_000e6 + 1, bob);

        vm.prank(owner);
        vault.setDepositsPaused(true);
        assertEq(vault.maxDeposit(bob), 0);
    }

    function test_performanceFeeCapped() public {
        vm.prank(owner);
        vm.expectRevert(SluiceVault.FeeTooHigh.selector);
        vault.setPerformanceFee(3_001);
    }

    function test_setWithdrawQueueRejectsDuplicates() public {
        IStrategy[] memory queue = new IStrategy[](2);
        queue[0] = strategyA;
        queue[1] = strategyA;
        vm.prank(owner);
        vm.expectRevert(SluiceVault.StrategyMismatch.selector);
        vault.setWithdrawQueue(queue);
    }

    function test_twoStepOwnership() public {
        vm.prank(owner);
        vault.transferOwnership(bob);
        assertEq(vault.owner(), owner);
        vm.prank(bob);
        vault.acceptOwnership();
        assertEq(vault.owner(), bob);
    }
}
