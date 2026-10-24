// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {Test} from "forge-std/Test.sol";
import {Token} from "../workspace/src/Token.sol";
import {Protocol} from "../workspace/src/Protocol.sol";
import {IVoteToken} from "../workspace/src/interfaces/IVoteToken.sol";
import {Deploy} from "../workspace/script/Deploy.s.sol";

interface ITokenGovernor {
    function propose(address[] memory, uint256[] memory, bytes[] memory, string memory) external returns (uint256);
    function castVote(uint256, uint8) external returns (uint256);
    function queue(address[] memory, uint256[] memory, bytes[] memory, bytes32) external returns (uint256);
    function execute(address[] memory, uint256[] memory, bytes[] memory, bytes32) external payable returns (uint256);
    function state(uint256) external view returns (uint8);
    function proposalSnapshot(uint256) external view returns (uint256);
    function proposalDeadline(uint256) external view returns (uint256);
    function votingDelay() external view returns (uint256);
    function votingPeriod() external view returns (uint256);
    function quorum(uint256) external view returns (uint256);
    function token() external view returns (address);
    function clock() external view returns (uint48);
    function CLOCK_MODE() external view returns (string memory);
}

contract TokenGovernorTest is Test {
    address constant A = address(0xA11CE);
    address constant B = address(0xB0B);
    address constant STRANGER = address(0xCA11);
    address constant RECIPIENT = address(0xF00D);
    uint8 constant ACTIVE = 1;
    uint8 constant DEFEATED = 3;
    uint8 constant SUCCEEDED = 4;
    uint8 constant EXECUTED = 7;

    struct Proposal {
        uint256 id;
        address[] targets;
        uint256[] values;
        bytes[] data;
        bytes32 descriptionHash;
    }

    Token token;
    Protocol protocol;
    Deploy deployer;
    ITokenGovernor governor;
    IVoteToken votes;
    bool timestampClock;

    function setUp() public {
        vm.warp(1_800_000_000);
        vm.roll(1_000_000);
        token = new Token();
        protocol = new Protocol();
        deployer = new Deploy();
        (address governorAddress, address holder) = deployer.run(address(token));
        governor = ITokenGovernor(governorAddress);
        protocol.transferOwnership(holder);
        vm.deal(holder, 3 ether);
        votes = IVoteToken(governor.token());
        string memory mode = governor.CLOCK_MODE();
        timestampClock = startsWith(mode, "mode=timestamp");
        assertTrue(timestampClock || startsWith(mode, "mode=blocknumber"), "unsupported governor clock");
        assertEq(votes.CLOCK_MODE(), mode, "vote token and governor clocks differ");
        assertEq(uint256(governor.clock()), timestampClock ? block.timestamp : block.number, "clock reports wrong time");
    }

    function startsWith(string memory text, string memory prefix) internal pure returns (bool) {
        bytes memory value = bytes(text);
        bytes memory head = bytes(prefix);
        if (value.length < head.length) return false;
        for (uint256 i; i < head.length; ++i) if (value[i] != head[i]) return false;
        return true;
    }

    function advanceTo(uint256 point) internal {
        uint256 current = governor.clock();
        require(point >= current, "cannot move clock backwards");
        uint256 distance = point - current;
        if (timestampClock) {
            vm.warp(point);
            vm.roll(block.number + (distance + 11) / 12);
        } else {
            vm.roll(point);
            vm.warp(block.timestamp + distance * 12);
        }
        assertEq(uint256(governor.clock()), point, "governor clock did not advance");
    }

    function waitSeconds(uint256 seconds_) internal {
        vm.warp(block.timestamp + seconds_);
        vm.roll(block.number + (seconds_ + 11) / 12);
    }

    function wrap(address who, uint256 amount) internal {
        token.transfer(who, amount);
        vm.startPrank(who);
        token.approve(address(votes), amount);
        assertTrue(votes.depositFor(who, amount), "wrap failed");
        votes.delegate(who);
        vm.stopPrank();
        assertEq(votes.getVotes(who), votes.balanceOf(who), "wrapped TOKEN did not become votes");
    }

    function propose(address target, uint256 value, bytes memory data, string memory description)
        internal returns (Proposal memory p)
    {
        advanceTo(uint256(governor.clock()) + 1);
        p.targets = new address[](1);
        p.values = new uint256[](1);
        p.data = new bytes[](1);
        p.targets[0] = target;
        p.values[0] = value;
        p.data[0] = data;
        p.descriptionHash = keccak256(bytes(description));
        uint256 proposedAt = governor.clock();
        vm.prank(A);
        p.id = governor.propose(p.targets, p.values, p.data, description);
        assertEq(governor.proposalSnapshot(p.id), proposedAt + governor.votingDelay(), "wrong voting delay");
        assertEq(governor.proposalDeadline(p.id), governor.proposalSnapshot(p.id) + governor.votingPeriod(), "wrong voting period");
        advanceTo(governor.proposalSnapshot(p.id) + 1);
        assertEq(governor.state(p.id), ACTIVE, "proposal did not become active");
    }

    function feeProposal(uint256 fee, string memory description) internal returns (Proposal memory) {
        return propose(address(protocol), 0, abi.encodeCall(Protocol.setFee, (fee)), description);
    }

    function vote(Proposal memory p, address who, uint8 support, uint256 weight) internal {
        vm.prank(who);
        assertEq(governor.castVote(p.id, support), weight, "wrong voting weight");
    }

    function finish(Proposal memory p, uint8 expected) internal {
        advanceTo(governor.proposalDeadline(p.id) + 1);
        assertEq(governor.state(p.id), expected, "wrong proposal outcome");
    }

    function queue(Proposal memory p) internal {
        governor.queue(p.targets, p.values, p.data, p.descriptionHash);
    }

    function execute(Proposal memory p) internal {
        vm.prank(STRANGER);
        governor.execute(p.targets, p.values, p.data, p.descriptionHash);
        assertEq(governor.state(p.id), EXECUTED, "proposal was not executed");
    }

    function pass(Proposal memory p) internal {
        vote(p, A, 1, 5_000_000 ether);
        finish(p, SUCCEEDED);
    }

    function test_quorumCountsTheWholeSupply() public {
        wrap(A, 1_000_000 ether);
        Proposal memory small = feeProposal(1, "one percent");
        vote(small, A, 1, 1_000_000 ether);
        finish(small, DEFEATED);
        assertEq(protocol.fee(), 0, "defeated proposal changed the fee");
        assertEq(governor.quorum(governor.proposalSnapshot(small.id)), 4_000_000 ether, "quorum does not use TOKEN supply");

        wrap(B, 4_000_000 ether);
        Proposal memory enough = feeProposal(7, "five percent");
        vote(enough, A, 1, 1_000_000 ether);
        vote(enough, B, 1, 4_000_000 ether);
        finish(enough, SUCCEEDED);
        queue(enough);
        waitSeconds(2 days);
        execute(enough);
        assertEq(protocol.fee(), 7, "passed proposal did not control Protocol");

        Proposal memory abstain = feeProposal(8, "abstentions are not for votes");
        vote(abstain, A, 1, 1_000_000 ether);
        vote(abstain, B, 2, 4_000_000 ether);
        finish(abstain, DEFEATED);

        wrap(STRANGER, 5_000_000 ether);
        Proposal memory opposed = feeProposal(8, "equal for and against");
        vote(opposed, A, 1, 1_000_000 ether);
        vote(opposed, B, 1, 4_000_000 ether);
        vote(opposed, STRANGER, 0, 5_000_000 ether);
        finish(opposed, DEFEATED);

        Proposal memory boundary = feeProposal(9, "exactly four percent");
        vote(boundary, A, 0, 1_000_000 ether);
        vote(boundary, B, 1, 4_000_000 ether);
        finish(boundary, SUCCEEDED);
        queue(boundary);
        waitSeconds(2 days);
        execute(boundary);
        assertEq(protocol.fee(), 9, "four percent for must suffice");
    }

    function test_theDelayGuardsTheMoney() public {
        wrap(A, 5_000_000 ether);
        address owner = protocol.owner();
        assertTrue(owner.code.length != 0, "Protocol owner is not an executor contract");
        assertTrue(owner != address(governor) && owner != address(deployer) && owner != address(this),
            "Protocol owner bypasses the wait");
        address[4] memory callers = [address(governor), address(deployer), address(this), STRANGER];
        for (uint256 i; i < callers.length; ++i) {
            vm.prank(callers[i]);
            vm.expectRevert();
            protocol.setFee(99);
        }

        Proposal memory payment = propose(RECIPIENT, 1 ether, "", "treasury payment");
        pass(payment);
        vm.expectRevert();
        governor.execute(payment.targets, payment.values, payment.data, payment.descriptionHash);
        queue(payment);
        waitSeconds(2 days - 1 hours);
        vm.expectRevert();
        governor.execute(payment.targets, payment.values, payment.data, payment.descriptionHash);
        assertEq(RECIPIENT.balance, 0, "treasury paid before two days");
        waitSeconds(1 hours);
        execute(payment);
        assertEq(RECIPIENT.balance, 1 ether, "treasury did not pay after two days");
        assertEq(owner.balance, 2 ether, "payment did not come from the owner");

        Proposal memory setter = feeProposal(42, "protocol owner call");
        pass(setter);
        queue(setter);
        waitSeconds(2 days - 1 hours);
        vm.expectRevert();
        governor.execute(setter.targets, setter.values, setter.data, setter.descriptionHash);
        assertEq(protocol.fee(), 0, "owner call bypassed the wait");
        waitSeconds(1 hours);
        execute(setter);
        assertEq(protocol.fee(), 42, "timed owner call failed");

        Proposal memory shorten = propose(owner, 0, abi.encodeWithSignature("updateDelay(uint256)", 0), "remove delay");
        pass(shorten);
        queue(shorten);
        waitSeconds(2 days - 1 hours);
        vm.expectRevert();
        governor.execute(shorten.targets, shorten.values, shorten.data, shorten.descriptionHash);
        waitSeconds(1 hours);
        execute(shorten);
        // A fresh payment proves that the delay change actually took effect.
        Proposal memory immediate = propose(RECIPIENT, 1 ether, "", "payment after delay change");
        pass(immediate);
        queue(immediate);
        execute(immediate);
        assertEq(RECIPIENT.balance, 2 ether, "delay change did not execute");
    }

    function test_lateVotesExtendTheVote() public {
        wrap(A, 1_000_000 ether);
        wrap(B, 4_000_000 ether);
        // Establish that ordinary votes can pass before trying the late vote.
        Proposal memory ordinary = feeProposal(1, "ordinary vote");
        vote(ordinary, A, 1, 1_000_000 ether);
        vote(ordinary, B, 1, 4_000_000 ether);
        finish(ordinary, SUCCEEDED);

        Proposal memory late = feeProposal(2, "late quorum");
        vote(late, A, 0, 1_000_000 ether);
        uint256 oldDeadline = governor.proposalDeadline(late.id);
        uint256 hour = timestampClock ? 1 hours : 1 hours / 12;
        uint256 activeAt = governor.clock();
        // Short voting periods still get a vote just before their deadline.
        uint256 remaining = oldDeadline - activeAt;
        advanceTo(remaining > hour ? oldDeadline - hour : activeAt);
        vote(late, B, 1, 4_000_000 ether);
        uint256 extended = governor.proposalDeadline(late.id);
        assertGt(extended, oldDeadline, "late quorum did not extend the deadline");
        advanceTo(oldDeadline);
        assertEq(governor.state(late.id), ACTIVE, "vote closed at its former deadline");
        finish(late, SUCCEEDED);
    }

    function test_snapshotCanRunIt() public {
        wrap(A, 5_000_000 ether);
        assertEq(votes.delegates(A), A, "delegation view is wrong");
        Proposal memory ordinary = feeProposal(1, "historical votes work");
        uint256 firstSnapshot = governor.proposalSnapshot(ordinary.id);
        assertEq(votes.getPastVotes(A, firstSnapshot), 5_000_000 ether, "past votes are missing");
        assertEq(votes.getPastTotalSupply(firstSnapshot), 5_000_000 ether, "past vote supply is missing");
        pass(ordinary);

        Proposal memory late = feeProposal(2, "tokens acquired after snapshot");
        uint256 snapshot = governor.proposalSnapshot(late.id);
        wrap(B, 5_000_000 ether);
        advanceTo(uint256(governor.clock()) + 1);
        assertEq(votes.getVotes(B), 5_000_000 ether, "new holder has no current votes");
        assertEq(votes.getPastVotes(B, snapshot), 0, "new votes changed the past");
        assertEq(votes.getPastTotalSupply(snapshot), 5_000_000 ether, "new deposits changed past supply");
        vm.prank(B);
        try governor.castVote(late.id, 1) returns (uint256 weight) {
            assertEq(weight, 0, "late holder voted with current power");
        } catch {}
        finish(late, DEFEATED);

        vm.prank(B);
        assertTrue(votes.withdrawTo(B, 5_000_000 ether), "withdrawal failed");
        assertEq(token.balanceOf(B), 5_000_000 ether, "withdrawal did not return TOKEN one to one");
        assertEq(votes.balanceOf(B), 0, "withdrawal did not burn receipts");
    }
}
