// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {BaseTest} from "./Base.t.sol";
import {BallastStaking} from "../src/BallastStaking.sol";

contract BallastStakingTest is BaseTest {
    function test_stakeMintsSharesOneToOne() public {
        uint256 shares = _stake(alice, 100e18);
        assertEq(shares, 100e18);
        assertEq(staking.totalAssets(), 100e18);
        assertEq(staking.balanceOf(alice), 100e18);
    }

    function test_stakeBelowMinimumReverts() public {
        vm.prank(alice);
        vm.expectRevert(BallastStaking.BelowMinimum.selector);
        staking.stake(1e17, alice);
    }

    function test_withdrawalAfterCooldown() public {
        _stake(alice, 100e18);
        vm.prank(alice);
        uint256 id = staking.requestWithdrawal(40e18);
        assertEq(staking.totalQueued(), 40e18);
        assertEq(staking.balanceOf(alice), 60e18);

        vm.prank(alice);
        vm.expectRevert(BallastStaking.CooldownActive.selector);
        staking.claimWithdrawal(id, alice);

        vm.warp(block.timestamp + 10 days);
        vm.prank(alice);
        staking.claimWithdrawal(id, alice);
        assertEq(blst.balanceOf(alice), 940e18);
        assertEq(staking.totalQueued(), 0);
    }

    function test_onlyOwnerClaims() public {
        _stake(alice, 100e18);
        vm.prank(alice);
        uint256 id = staking.requestWithdrawal(100e18);
        vm.warp(block.timestamp + 10 days);
        vm.prank(bob);
        vm.expectRevert(BallastStaking.NotWithdrawalOwner.selector);
        staking.claimWithdrawal(id, bob);
    }

    function test_cancelRestoresPosition() public {
        _stake(alice, 100e18);
        _stake(bob, 100e18);
        vm.prank(alice);
        uint256 id = staking.requestWithdrawal(50e18);
        vm.prank(alice);
        staking.cancelWithdrawal(id);
        assertEq(staking.balanceOf(alice), 100e18);
        assertEq(staking.totalQueued(), 0);
        assertEq(staking.totalAssets(), 200e18);
    }

    function test_feesStreamOverTheWeek() public {
        _stake(alice, 100e18);
        _stake(bob, 300e18);
        _collectFees(100e18);

        assertEq(blst.balanceOf(treasury), 20e18);
        assertEq(staking.totalAssets(), 400e18);

        vm.warp(block.timestamp + 3.5 days);
        assertApproxEqAbs(staking.totalAssets(), 440e18, 1e6);

        vm.warp(block.timestamp + 7 days);
        assertApproxEqAbs(staking.balanceOf(alice), 120e18, 1e6);
        assertApproxEqAbs(staking.balanceOf(bob), 360e18, 1e6);
    }

    function test_lateStakerDoesNotTakeVestedRewards() public {
        _stake(alice, 100e18);
        _collectFees(70e18);
        vm.warp(block.timestamp + 7 days);

        _stake(bob, 100e18);
        assertApproxEqAbs(staking.balanceOf(alice), 156e18, 1e6);
        assertApproxEqAbs(staking.balanceOf(bob), 100e18, 1e6);
    }

    function test_harvestWithNothingNewOnlyAddsDust() public {
        _stake(alice, 100e18);
        _collectFees(10e18);
        uint256 unvested = staking.unvestedRewards();
        assertLt(staking.harvest(), staking.REWARD_PERIOD());
        assertApproxEqAbs(staking.unvestedRewards(), unvested, staking.REWARD_PERIOD());
    }

    function test_fullExitAfterRewards() public {
        _stake(alice, 100e18);
        _collectFees(50e18);
        vm.warp(block.timestamp + 7 days);

        uint256 shares = staking.sharesOf(alice);
        vm.prank(alice);
        uint256 id = staking.requestWithdrawal(shares);
        vm.warp(block.timestamp + 10 days);
        vm.prank(alice);
        uint256 paid = staking.claimWithdrawal(id, alice);
        assertApproxEqAbs(paid, 140e18, 1e6);
    }

    function test_pauseBlocksStakeButNotExit() public {
        _stake(alice, 100e18);
        vm.prank(governance);
        staking.setPaused(true);

        vm.prank(bob);
        vm.expectRevert(BallastStaking.Paused.selector);
        staking.stake(10e18, bob);

        vm.prank(alice);
        uint256 id = staking.requestWithdrawal(100e18);
        vm.warp(block.timestamp + 10 days);
        vm.prank(alice);
        staking.claimWithdrawal(id, alice);
    }

    function test_cooldownBounds() public {
        vm.startPrank(governance);
        vm.expectRevert(BallastStaking.InvalidCooldown.selector);
        staking.setCooldown(31 days);
        staking.setCooldown(14 days);
        vm.stopPrank();
        assertEq(staking.cooldown(), 14 days);
    }

    function test_ownershipTwoStep() public {
        vm.prank(governance);
        staking.transferOwnership(bob);
        assertEq(staking.owner(), governance);
        vm.prank(bob);
        staking.acceptOwnership();
        assertEq(staking.owner(), bob);
    }
}
