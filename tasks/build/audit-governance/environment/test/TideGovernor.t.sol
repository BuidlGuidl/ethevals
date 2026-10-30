// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {Base} from "./Base.t.sol";
import {TideGovernor} from "../src/TideGovernor.sol";
import {TideTimelock} from "../src/TideTimelock.sol";

contract TideGovernorTest is Base {
    address internal grantee = makeAddr("grantee");

    function setUp() public override {
        super.setUp();
        _lock(alice, 500_000e18, 104 weeks);
        _lock(bob, 300_000e18, 104 weeks);
        _lock(carol, 100_000e18, 104 weeks);
        vm.warp(block.timestamp + 1);
    }

    function _propose(string memory description) internal returns (uint256 id) {
        (address[] memory t, uint256[] memory v, bytes[] memory c,) = _grantProposal(grantee, 50_000e18, description);
        vm.prank(alice);
        id = governor.propose(t, v, c, description);
    }

    function test_fullLifecycle() public {
        string memory description = "Grant 50k TIDE to grantee";
        uint256 id = _propose(description);
        assertEq(uint8(governor.state(id)), uint8(TideGovernor.ProposalState.Pending));

        vm.warp(block.timestamp + VOTING_DELAY + 1);
        assertEq(uint8(governor.state(id)), uint8(TideGovernor.ProposalState.Active));
        vm.prank(alice);
        governor.castVote(id, 1);
        vm.prank(bob);
        governor.castVote(id, 0);
        vm.prank(alice);
        vm.expectRevert(TideGovernor.AlreadyVoted.selector);
        governor.castVote(id, 1);

        vm.warp(block.timestamp + VOTING_PERIOD);
        assertEq(uint8(governor.state(id)), uint8(TideGovernor.ProposalState.Succeeded));

        (address[] memory t, uint256[] memory v, bytes[] memory c, bytes32 h) = _grantProposal(grantee, 50_000e18, description);
        governor.queue(t, v, c, h);
        assertEq(uint8(governor.state(id)), uint8(TideGovernor.ProposalState.Queued));

        vm.expectRevert(TideTimelock.NotReady.selector);
        governor.execute(t, v, c, h);

        vm.warp(block.timestamp + DELAY);
        governor.execute(t, v, c, h);
        assertEq(tide.balanceOf(grantee), 50_000e18);
        assertEq(uint8(governor.state(id)), uint8(TideGovernor.ProposalState.Executed));
    }

    function test_defeatedWithoutQuorum() public {
        string memory description = "Small grant";
        uint256 id = _propose(description);
        vm.warp(block.timestamp + VOTING_DELAY + 1);
        vm.prank(carol);
        governor.castVote(id, 1);
        vm.warp(block.timestamp + VOTING_PERIOD);
        assertEq(uint8(governor.state(id)), uint8(TideGovernor.ProposalState.Defeated));

        (address[] memory t, uint256[] memory v, bytes[] memory c, bytes32 h) = _grantProposal(grantee, 50_000e18, description);
        vm.expectRevert(abi.encodeWithSelector(TideGovernor.WrongState.selector, TideGovernor.ProposalState.Defeated));
        governor.queue(t, v, c, h);
    }

    function test_proposerNeedsThreshold() public {
        address nobody = makeAddr("nobody");
        (address[] memory t, uint256[] memory v, bytes[] memory c,) = _grantProposal(grantee, 1, "x");
        vm.prank(nobody);
        vm.expectRevert(TideGovernor.BelowThreshold.selector);
        governor.propose(t, v, c, "x");
    }

    function test_votesUseSnapshot() public {
        uint256 id = _propose("Snapshot grant");
        vm.warp(block.timestamp + VOTING_DELAY + 1);
        vm.prank(carol);
        escrow.increaseAmount(400_000e18);
        vm.prank(carol);
        uint256 weight = governor.castVote(id, 1);
        assertLt(weight, 100_000e18);
    }

    function test_proposerCancelsWhilePending() public {
        string memory description = "Withdrawn idea";
        uint256 id = _propose(description);
        (address[] memory t, uint256[] memory v, bytes[] memory c, bytes32 h) = _grantProposal(grantee, 50_000e18, description);
        vm.prank(bob);
        vm.expectRevert(TideGovernor.NotAllowed.selector);
        governor.cancel(t, v, c, h);
        vm.prank(alice);
        governor.cancel(t, v, c, h);
        assertEq(uint8(governor.state(id)), uint8(TideGovernor.ProposalState.Canceled));
    }

    function test_guardianCancelsQueuedProposal() public {
        string memory description = "Contested grant";
        uint256 id = _propose(description);
        vm.warp(block.timestamp + VOTING_DELAY + 1);
        vm.prank(alice);
        governor.castVote(id, 1);
        vm.warp(block.timestamp + VOTING_PERIOD);
        (address[] memory t, uint256[] memory v, bytes[] memory c, bytes32 h) = _grantProposal(grantee, 50_000e18, description);
        governor.queue(t, v, c, h);

        vm.prank(guardian);
        governor.cancel(t, v, c, h);
        assertEq(uint8(governor.state(id)), uint8(TideGovernor.ProposalState.Canceled));

        vm.warp(block.timestamp + DELAY);
        vm.expectRevert(abi.encodeWithSelector(TideGovernor.WrongState.selector, TideGovernor.ProposalState.Canceled));
        governor.execute(t, v, c, h);
    }

    function test_onlyGovernorSchedules() public {
        (address[] memory t, uint256[] memory v, bytes[] memory c, bytes32 h) = _grantProposal(grantee, 1, "x");
        vm.expectRevert(TideTimelock.NotGovernor.selector);
        timelock.schedule(t, v, c, h, DELAY);
        vm.expectRevert(TideTimelock.NotTimelock.selector);
        timelock.setMinDelay(3 days);
        vm.expectRevert(TideGovernor.NotTimelock.selector);
        governor.updateSettings(1, 1, 1, 1);
    }
}
