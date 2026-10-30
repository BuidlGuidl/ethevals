// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {BaseTest} from "ballast/test/Base.t.sol";
import {SafeTransfer} from "ballast/src/libraries/SafeTransfer.sol";

contract HighsTest is BaseTest {
    /// H-01: harvest() counts BLST owed to queued withdrawals as new rewards. Anyone can call it,
    /// and FeeRouter.distribute() calls it on every fee run. The queued BLST is streamed to the
    /// stakers who stayed, and the last withdrawal to be claimed finds the contract empty.
    function test_H01_harvestStreamsQueuedWithdrawalsToStakers() public {
        _stake(alice, 100e18);
        _stake(bob, 100e18);

        uint256 aliceShares = staking.sharesOf(alice);
        vm.prank(alice);
        uint256 aliceId = staking.requestWithdrawal(aliceShares);
        assertEq(staking.totalQueued(), 100e18);

        // No fees arrived, yet a harvest finds 100 BLST to stream.
        uint256 added = staking.harvest();
        assertEq(added, 100e18, "queued BLST counted as rewards");

        vm.warp(block.timestamp + 7 days);
        assertApproxEqAbs(staking.balanceOf(bob), 200e18, 1e6, "bob's stake now includes alice's queued BLST");

        uint256 bobShares = staking.sharesOf(bob);
        vm.prank(bob);
        uint256 bobId = staking.requestWithdrawal(bobShares);
        vm.warp(block.timestamp + 10 days);
        vm.prank(bob);
        uint256 bobPaid = staking.claimWithdrawal(bobId, bob);
        assertApproxEqAbs(bobPaid, 200e18, 1e6);

        assertLt(blst.balanceOf(address(staking)), 100e18, "contract cannot pay alice");
        vm.prank(alice);
        vm.expectRevert(SafeTransfer.TransferFailed.selector);
        staking.claimWithdrawal(aliceId, alice);
    }

    /// H-02: requestWithdrawal() fixes the BLST owed at queue time and slash() only takes from
    /// active stake. A staker who queues after a slash is proposed, during the public delay, pays
    /// none of it, and the stakers who stayed pay their share as well.
    function test_H02_queuedWithdrawalEscapesProposedSlash() public {
        _stake(alice, 100e18);
        _stake(bob, 100e18);

        vm.prank(governance);
        uint256 proposal = shortfall.proposeSlash(40e18, market, "bad debt in the USDC market");

        // Alice sees the proposal and queues her whole position before it executes.
        uint256 aliceShares = staking.sharesOf(alice);
        vm.prank(alice);
        uint256 aliceId = staking.requestWithdrawal(aliceShares);

        vm.warp(block.timestamp + 2 days);
        assertEq(shortfall.executeSlash(proposal), 30e18, "only 30% of the active 100 BLST is slashable");

        // Pro rata, each staker would keep 80 BLST. Bob keeps 70, alice keeps all 100,
        // and the market recovers 30 instead of 40.
        assertEq(staking.balanceOf(bob), 70e18);
        vm.warp(block.timestamp + 10 days);
        vm.prank(alice);
        assertEq(staking.claimWithdrawal(aliceId, alice), 100e18);
    }

    /// H-02, second path: with a slash that fits under the cap, the stakers who stayed pay
    /// the queued staker's share.
    function test_H02_stayingStakersPayTheQueuedShare() public {
        _stake(alice, 100e18);
        _stake(bob, 300e18);

        vm.prank(governance);
        uint256 proposal = shortfall.proposeSlash(40e18, market, "bad debt");
        uint256 aliceShares = staking.sharesOf(alice);
        vm.prank(alice);
        uint256 aliceId = staking.requestWithdrawal(aliceShares);

        vm.warp(block.timestamp + 2 days);
        assertEq(shortfall.executeSlash(proposal), 40e18);

        // Pro rata: alice 90, bob 270. Actual: alice 100, bob 260.
        assertEq(staking.balanceOf(bob), 260e18);
        vm.warp(block.timestamp + 10 days);
        vm.prank(alice);
        assertEq(staking.claimWithdrawal(aliceId, alice), 100e18);
    }
}
