// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {Base} from "./Base.t.sol";
import {VoteEscrow} from "../src/VoteEscrow.sol";

contract VoteEscrowTest is Base {
    function test_createLockGivesDecayingPower() public {
        _lock(alice, 104_000e18, 104 weeks);
        (uint128 amount, uint48 end) = escrow.locks(alice);
        assertEq(amount, 104_000e18);
        assertEq(end % escrow.WEEK(), 0);

        uint256 start = escrow.getVotes(alice);
        assertGt(start, 103_000e18);
        assertLe(start, 104_000e18);

        vm.warp(block.timestamp + 52 weeks);
        assertApproxEqRel(escrow.getVotes(alice), start / 2, 0.01e18);

        vm.warp(end);
        assertEq(escrow.getVotes(alice), 0);
    }

    function test_rejectsBadLocks() public {
        vm.startPrank(alice);
        vm.expectRevert(VoteEscrow.ZeroAmount.selector);
        escrow.createLock(0, block.timestamp + 10 weeks);
        vm.expectRevert(VoteEscrow.BadUnlockTime.selector);
        escrow.createLock(1e18, block.timestamp + 105 weeks);
        vm.expectRevert(VoteEscrow.BadUnlockTime.selector);
        escrow.createLock(1e18, block.timestamp);
        escrow.createLock(1e18, block.timestamp + 10 weeks);
        vm.expectRevert(VoteEscrow.LockExists.selector);
        escrow.createLock(1e18, block.timestamp + 10 weeks);
        vm.stopPrank();
    }

    function test_increaseAndExtend() public {
        _lock(alice, 10_000e18, 20 weeks);
        vm.warp(block.timestamp + 1 days);
        uint256 before = escrow.getVotes(alice);

        vm.prank(alice);
        escrow.increaseAmount(10_000e18);
        assertApproxEqAbs(escrow.getVotes(alice), before * 2, 1);

        (, uint48 end) = escrow.locks(alice);
        vm.warp(block.timestamp + 1 days);
        vm.prank(alice);
        escrow.extendLock(uint256(end) + 20 weeks);
        assertGt(escrow.getVotes(alice), before * 2 - 1);
        assertEq(escrow.totalLocked(), 20_000e18);
        assertEq(escrow.numCheckpoints(alice), 3);
    }

    function test_pastVotesFollowHistory() public {
        _lock(alice, 10_000e18, 52 weeks);
        uint256 t1 = block.timestamp;
        vm.warp(t1 + 1 weeks);
        vm.prank(alice);
        escrow.increaseAmount(30_000e18);
        uint256 t2 = block.timestamp;
        vm.warp(t2 + 1 weeks);

        assertEq(escrow.getPastVotes(alice, t1 - 1), 0);
        (, uint48 end) = escrow.locks(alice);
        assertEq(escrow.getPastVotes(alice, t1), 10_000e18 * (end - t1) / escrow.MAX_LOCK());
        assertEq(escrow.getPastVotes(alice, t2), 40_000e18 * (end - t2) / escrow.MAX_LOCK());
        assertApproxEqAbs(escrow.getPastVotes(alice, block.timestamp - 1), escrow.getVotes(alice) + 40_000e18 / escrow.MAX_LOCK(), 1);

        vm.expectRevert(VoteEscrow.FutureLookup.selector);
        escrow.getPastVotes(alice, block.timestamp);
    }

    function test_withdrawAfterExpiry() public {
        _lock(alice, 10_000e18, 4 weeks);
        vm.prank(alice);
        vm.expectRevert(VoteEscrow.LockNotExpired.selector);
        escrow.withdraw();

        (, uint48 end) = escrow.locks(alice);
        vm.warp(end);
        uint256 before = tide.balanceOf(alice);
        vm.prank(alice);
        escrow.withdraw();
        assertEq(tide.balanceOf(alice) - before, 10_000e18);
        assertEq(escrow.totalLocked(), 0);
        assertEq(escrow.getVotes(alice), 0);
    }

    function test_exitEarlyPaysPenaltyToTreasury() public {
        _lock(alice, 104_000e18, 104 weeks);
        vm.warp(block.timestamp + 52 weeks);
        uint256 power = escrow.getVotes(alice);
        uint256 treasuryBefore = tide.balanceOf(address(timelock));
        uint256 aliceBefore = tide.balanceOf(alice);

        vm.prank(alice);
        escrow.exitEarly();

        assertEq(tide.balanceOf(address(timelock)) - treasuryBefore, power / 2);
        assertEq(tide.balanceOf(alice) - aliceBefore, 104_000e18 - power / 2);
        assertEq(escrow.getVotes(alice), 0);
        assertEq(escrow.totalLocked(), 0);
        assertEq(tide.balanceOf(address(escrow)), 0);
    }

    function test_relockAfterExit() public {
        _lock(alice, 10_000e18, 30 weeks);
        vm.prank(alice);
        escrow.exitEarly();
        _lock(alice, 5_000e18, 10 weeks);
        (uint128 amount,) = escrow.locks(alice);
        assertEq(amount, 5_000e18);
    }
}
