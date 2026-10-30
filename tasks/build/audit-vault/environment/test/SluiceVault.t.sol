// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {SluiceFixture} from "./SluiceFixture.sol";
import {SluiceVault} from "../src/SluiceVault.sol";
import {SluiceConfig} from "../src/SluiceConfig.sol";
import {AaveV3Strategy} from "../src/strategies/AaveV3Strategy.sol";
import {IStrategy} from "../src/interfaces/IStrategy.sol";
import {BaseStrategy} from "../src/strategies/BaseStrategy.sol";

contract SluiceVaultTest is SluiceFixture {
    function test_metadata() public view {
        assertEq(vault.asset(), address(usdc));
        assertEq(vault.decimals(), 12);
        assertEq(vault.withdrawQueueLength(), 2);
        assertEq(vault.timelock(), 1 days);
        assertEq(vault.guardian(), guardian);
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

    function test_mintAndWithdrawRoundTrip() public {
        uint256 shares = vault.previewDeposit(50_000e6);
        vm.prank(alice);
        uint256 assets = vault.mint(shares, alice);
        assertEq(assets, 50_000e6);

        vm.prank(alice);
        vault.withdraw(50_000e6, alice, alice);
        assertEq(vault.balanceOf(alice), 0);
    }

    function test_withdrawWithAllowance() public {
        uint256 shares = _deposit(alice, 10_000e6);
        vm.prank(alice);
        vault.approve(bob, shares);
        vm.prank(bob);
        vault.redeem(shares, bob, alice);
        assertEq(usdc.balanceOf(bob), 1_010_000e6);
        assertEq(vault.allowance(alice, bob), 0);
    }

    function test_allocateMovesIdleIntoStrategy() public {
        _deposit(alice, 500_000e6);
        vm.prank(allocator);
        vault.allocate(strategyA, 300_000e6);

        assertEq(usdc.balanceOf(address(vault)), 200_000e6);
        assertEq(strategyA.totalAssets(), 300_000e6);
        assertEq(strategyA.deployedAssets(), 300_000e6);
        assertEq(vault.totalAssets(), 500_000e6);
    }

    function test_allocateIntoAaveStrategy() public {
        _deposit(alice, 400_000e6);
        vm.prank(allocator);
        vault.allocate(strategyB, 400_000e6);

        assertEq(strategyB.totalAssets(), 400_000e6);
        assertEq(strategyB.maxUndeploy(), 400_000e6);
        assertEq(vault.totalAssets(), 400_000e6);
    }

    function test_allocateRespectsCap() public {
        _deposit(alice, 1_000_000e6);
        _deposit(bob, 500_000e6);
        vm.prank(allocator);
        vm.expectRevert(SluiceVault.ExceedsCap.selector);
        vault.allocate(strategyA, 1_000_001e6);
    }

    function test_onlyAllocatorsAllocate() public {
        _deposit(alice, 100_000e6);
        vm.prank(alice);
        vm.expectRevert(SluiceConfig.Unauthorized.selector);
        vault.allocate(strategyA, 1e6);

        vm.prank(curator);
        vault.allocate(strategyA, 1e6);
        vm.prank(owner);
        vault.allocate(strategyA, 1e6);
    }

    function test_onlyVaultMovesStrategyFunds() public {
        vm.expectRevert();
        strategyA.undeploy(1e6);
        vm.expectRevert();
        strategyB.deploy(1e6);
        vm.expectRevert();
        strategyA.harvest();
    }

    function test_harvestChargesPerformanceFee() public {
        _deposit(alice, 1_000_000e6);
        vm.prank(allocator);
        vault.allocate(strategyA, 1_000_000e6);

        marketA.accrueInterest(40_000e6);
        vm.prank(allocator);
        vault.harvest(strategyA);

        assertApproxEqAbs(vault.accruedFees(), 6_000e6, 1);
        assertApproxEqAbs(strategyA.deployedAssets(), 1_040_000e6, 1);
    }

    function test_harvestAllCoversBothStrategyTypes() public {
        _deposit(alice, 1_000_000e6);
        vm.startPrank(allocator);
        vault.allocate(strategyA, 500_000e6);
        vault.allocate(strategyB, 500_000e6);
        vm.stopPrank();

        marketA.accrueInterest(10_000e6);
        aave.accrueInterest(20_000e6);
        vm.prank(allocator);
        vault.harvestAll();

        assertApproxEqAbs(vault.accruedFees(), 4_500e6, 2);
        assertApproxEqAbs(strategyB.deployedAssets(), 520_000e6, 1);
        assertGt(strategyA.lastHarvest(), 0);
    }

    function test_harvestBooksLossWithoutFee() public {
        _deposit(alice, 1_000_000e6);
        vm.prank(allocator);
        vault.allocate(strategyA, 500_000e6);

        vm.prank(address(marketA));
        usdc.transfer(address(0xdead), 10_000e6);
        vm.prank(allocator);
        vault.harvest(strategyA);

        assertEq(vault.accruedFees(), 0);
        assertEq(strategyA.deployedAssets(), 490_000e6);
    }

    function test_reallocateMovesBetweenStrategies() public {
        _deposit(alice, 600_000e6);
        vm.prank(allocator);
        vault.allocate(strategyA, 600_000e6);

        SluiceVault.Allocation[] memory plan = new SluiceVault.Allocation[](2);
        plan[0] = SluiceVault.Allocation(strategyA, 200_000e6);
        plan[1] = SluiceVault.Allocation(strategyB, type(uint256).max);
        vm.prank(allocator);
        vault.reallocate(plan);

        assertEq(strategyA.totalAssets(), 200_000e6);
        assertEq(strategyB.totalAssets(), 400_000e6);
        assertEq(usdc.balanceOf(address(vault)), 0);
    }

    function test_reallocateFillStopsAtCap() public {
        vm.prank(curator);
        vault.submitCap(strategyB, 100_000e6);
        _deposit(alice, 300_000e6);

        SluiceVault.Allocation[] memory plan = new SluiceVault.Allocation[](1);
        plan[0] = SluiceVault.Allocation(strategyB, type(uint256).max);
        vm.prank(allocator);
        vault.reallocate(plan);

        assertEq(strategyB.totalAssets(), 100_000e6);
        assertEq(usdc.balanceOf(address(vault)), 200_000e6);
    }

    function test_reallocateRejectsInactiveStrategy() public {
        SluiceVault.Allocation[] memory plan = new SluiceVault.Allocation[](1);
        plan[0] = SluiceVault.Allocation(IStrategy(address(0xbeef)), 1);
        vm.prank(allocator);
        vm.expectRevert(SluiceVault.StrategyInactive.selector);
        vault.reallocate(plan);
    }

    function test_withdrawPullsFromStrategiesInQueueOrder() public {
        _deposit(alice, 600_000e6);
        vm.startPrank(allocator);
        vault.allocate(strategyA, 300_000e6);
        vault.allocate(strategyB, 300_000e6);
        vm.stopPrank();

        vm.prank(alice);
        vault.withdraw(400_000e6, alice, alice);

        assertEq(strategyA.totalAssets(), 0);
        assertEq(strategyB.totalAssets(), 200_000e6);
        assertEq(usdc.balanceOf(alice), 800_000e6);
    }

    function test_curatorReordersWithdrawQueue() public {
        _deposit(alice, 600_000e6);
        vm.startPrank(allocator);
        vault.allocate(strategyA, 300_000e6);
        vault.allocate(strategyB, 300_000e6);
        vm.stopPrank();

        IStrategy[] memory queue = new IStrategy[](2);
        queue[0] = strategyB;
        queue[1] = strategyA;
        vm.prank(curator);
        vault.setWithdrawQueue(queue);
        assertEq(address(vault.withdrawQueue(0)), address(strategyB));

        vm.prank(alice);
        vault.withdraw(100_000e6, alice, alice);
        assertEq(strategyA.totalAssets(), 300_000e6);
        assertEq(strategyB.totalAssets(), 200_000e6);
    }

    function test_withdrawLimitedByMarketLiquidity() public {
        _deposit(alice, 100_000e6);
        vm.prank(allocator);
        vault.allocate(strategyA, 100_000e6);
        marketA.borrow(90_000e6);

        assertEq(vault.maxWithdraw(alice), 10_000e6);
        vm.prank(alice);
        vm.expectRevert(SluiceVault.ExceedsMaxWithdraw.selector);
        vault.withdraw(10_000e6 + 1, alice, alice);
    }

    function test_aaveLiquidityLimitsMaxWithdraw() public {
        _deposit(alice, 100_000e6);
        vm.prank(allocator);
        vault.allocate(strategyB, 100_000e6);
        aave.borrow(70_000e6);

        assertEq(strategyB.maxUndeploy(), 30_000e6);
        assertEq(vault.maxWithdraw(alice), 30_000e6);
        assertEq(vault.maxRedeem(alice), vault.convertToShares(30_000e6));
    }

    function test_pausedAaveReserveReturnsNothing() public {
        _deposit(alice, 100_000e6);
        vm.prank(allocator);
        vault.allocate(strategyB, 100_000e6);
        aave.setConfiguration((1 << 56) | (1 << 60));

        assertEq(strategyB.maxUndeploy(), 0);
        assertEq(vault.maxWithdraw(alice), 0);
    }

    function test_frozenAaveReserveRejectsSupply() public {
        _deposit(alice, 100_000e6);
        aave.setConfiguration((1 << 56) | (1 << 57));
        vm.prank(allocator);
        vm.expectRevert(AaveV3Strategy.ReserveUnavailable.selector);
        vault.allocate(strategyB, 100_000e6);
    }

    function test_removeStrategyReturnsEverything() public {
        _deposit(alice, 500_000e6);
        vm.prank(allocator);
        vault.allocate(strategyB, 500_000e6);

        vm.prank(curator);
        vault.removeStrategy(strategyB);

        assertEq(vault.withdrawQueueLength(), 1);
        assertEq(usdc.balanceOf(address(vault)), 500_000e6);
        assertEq(strategyB.deployedAssets(), 0);
        (bool active,) = vault.strategies(strategyB);
        assertFalse(active);
    }

    function test_depositLimit() public {
        vm.prank(curator);
        vault.setDepositLimit(150_000e6);
        _deposit(alice, 100_000e6);
        assertEq(vault.maxDeposit(bob), 50_000e6);
        assertEq(vault.maxMint(bob), vault.convertToShares(50_000e6));

        vm.prank(bob);
        vm.expectRevert(SluiceVault.ExceedsMaxDeposit.selector);
        vault.deposit(50_000e6 + 1, bob);
    }

    function test_guardianPausesDepositsNotWithdrawals() public {
        uint256 shares = _deposit(alice, 100_000e6);
        vm.prank(guardian);
        vault.pause();

        assertEq(vault.maxDeposit(bob), 0);
        assertEq(vault.maxMint(bob), 0);
        vm.prank(bob);
        vm.expectRevert(SluiceVault.ExceedsMaxDeposit.selector);
        vault.deposit(1e6, bob);
        vm.prank(allocator);
        vm.expectRevert(SluiceConfig.IsPaused.selector);
        vault.allocate(strategyA, 1e6);

        vm.prank(alice);
        vault.redeem(shares, alice, alice);
        assertEq(usdc.balanceOf(alice), 1_000_000e6);

        vm.prank(guardian);
        vm.expectRevert(SluiceConfig.Unauthorized.selector);
        vault.unpause();
        vm.prank(owner);
        vault.unpause();
        _deposit(bob, 1e6);
    }

    function test_managementFeeAccruesOverTime() public {
        vm.prank(owner);
        vault.submitManagementFee(200);
        skip(1 days);
        vault.acceptManagementFee();
        assertEq(vault.managementFee(), 200);

        _deposit(alice, 1_000_000e6);
        skip(365 days);
        vault.claimFees();

        assertApproxEqAbs(usdc.balanceOf(treasury), 20_000e6, 1);
        assertEq(vault.accruedFees(), 0);
    }

    function test_claimFeesRevertsWithNothingOwed() public {
        vm.expectRevert(SluiceVault.ZeroAmount.selector);
        vault.claimFees();
    }

    function test_setWithdrawQueueRejectsDuplicates() public {
        IStrategy[] memory queue = new IStrategy[](2);
        queue[0] = strategyA;
        queue[1] = strategyA;
        vm.prank(curator);
        vm.expectRevert(SluiceVault.StrategyMismatch.selector);
        vault.setWithdrawQueue(queue);
    }

    function test_interestReachesSharePriceAtHarvest() public {
        _deposit(alice, 1_000_000e6);
        vm.prank(allocator);
        vault.allocate(strategyA, 1_000_000e6);

        marketA.accrueInterest(40_000e6);
        assertEq(vault.totalAssets(), 1_000_000e6, "valued at the last harvest");
        vm.prank(allocator);
        vault.harvest(strategyA);
        assertApproxEqAbs(vault.totalAssets(), 1_000_000e6, 1, "profit starts locked");
    }

    function test_harvestedProfitUnlocksOverTime() public {
        _deposit(alice, 1_000_000e6);
        vm.prank(allocator);
        vault.allocate(strategyA, 1_000_000e6);
        marketA.accrueInterest(40_000e6);
        vm.prank(allocator);
        vault.harvest(strategyA);
        assertApproxEqAbs(vault.unlockingProfit(), 34_000e6, 1);

        skip(1 days);
        assertApproxEqAbs(vault.totalAssets(), 1_017_000e6, 1);
        skip(1 days);
        assertEq(vault.unlockingProfit(), 0);
        assertApproxEqAbs(vault.totalAssets(), 1_034_000e6, 1);
    }

    function test_lossTakenFromUnlockingProfitFirst() public {
        _deposit(alice, 1_000_000e6);
        vm.prank(allocator);
        vault.allocate(strategyA, 1_000_000e6);
        marketA.accrueInterest(40_000e6);
        vm.prank(allocator);
        vault.harvest(strategyA);

        vm.prank(address(marketA));
        usdc.transfer(address(0xdead), 10_000e6);
        vm.prank(allocator);
        vault.harvest(strategyA);

        assertApproxEqAbs(vault.unlockingProfit(), 24_000e6, 2);
        assertApproxEqAbs(vault.totalAssets(), 1_000_000e6, 2);
    }

    function test_withdrawalLowersHarvestBaseline() public {
        _deposit(alice, 500_000e6);
        vm.prank(allocator);
        vault.allocate(strategyA, 500_000e6);

        vm.prank(alice);
        vault.withdraw(200_000e6, alice, alice);
        assertEq(strategyA.deployedAssets(), 300_000e6);
    }

    function test_unclaimedFeesLeaveSharePrice() public {
        _deposit(alice, 1_000_000e6);
        vm.prank(allocator);
        vault.allocate(strategyA, 1_000_000e6);
        marketA.accrueInterest(40_000e6);
        vm.prank(allocator);
        vault.harvest(strategyA);
        skip(2 days);

        uint256 before = vault.totalAssets();
        vault.claimFees();
        assertEq(vault.totalAssets(), before);
    }

    function test_sellRewardsRejectsPositionAndAsset() public {
        address aToken = address(aave.aToken());
        vm.startPrank(allocator);
        vm.expectRevert(BaseStrategy.InvalidReward.selector);
        vault.sellRewards(strategyB, aToken, 0);
        vm.expectRevert(BaseStrategy.InvalidReward.selector);
        vault.sellRewards(strategyB, address(usdc), 0);
        vm.expectRevert(BaseStrategy.InvalidReward.selector);
        vault.sellRewards(strategyA, address(marketA), 0);
        vm.stopPrank();
    }

    function test_onlyAllocatorsSellRewards() public {
        vm.prank(alice);
        vm.expectRevert(SluiceConfig.Unauthorized.selector);
        vault.sellRewards(strategyB, address(rewardToken), 0);
    }

    function test_sellRewardsNeedsSwapper() public {
        vm.prank(owner);
        vault.setRewardSwapper(address(0));
        vm.prank(allocator);
        vm.expectRevert(SluiceVault.NoSwapper.selector);
        vault.sellRewards(strategyB, address(rewardToken), 0);
    }
}
