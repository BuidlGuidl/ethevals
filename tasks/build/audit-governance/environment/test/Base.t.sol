// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {Test} from "forge-std/Test.sol";
import {TideToken} from "../src/TideToken.sol";
import {VoteEscrow} from "../src/VoteEscrow.sol";
import {TideTimelock} from "../src/TideTimelock.sol";
import {TideGovernor} from "../src/TideGovernor.sol";

abstract contract Base is Test {
    TideToken internal tide;
    VoteEscrow internal escrow;
    TideTimelock internal timelock;
    TideGovernor internal governor;

    address internal deployer = makeAddr("deployer");
    address internal guardian = makeAddr("guardian");
    address internal alice = makeAddr("alice");
    address internal bob = makeAddr("bob");
    address internal carol = makeAddr("carol");

    uint256 internal constant DELAY = 2 days;
    uint256 internal constant VOTING_DELAY = 1 days;
    uint256 internal constant VOTING_PERIOD = 5 days;
    uint256 internal constant THRESHOLD = 10_000e18;
    uint256 internal constant QUORUM = 400_000e18;

    function setUp() public virtual {
        vm.warp(1_760_000_000);
        vm.startPrank(deployer);
        tide = new TideToken(deployer, 10_000_000e18);
        address predictedGovernor = vm.computeCreateAddress(deployer, vm.getNonce(deployer) + 2);
        timelock = new TideTimelock(predictedGovernor, DELAY);
        escrow = new VoteEscrow(tide, address(timelock));
        governor = new TideGovernor(escrow, timelock, guardian, VOTING_DELAY, VOTING_PERIOD, THRESHOLD, QUORUM);
        require(address(governor) == predictedGovernor, "governor address");

        tide.transfer(address(timelock), 2_000_000e18);
        tide.transfer(alice, 1_000_000e18);
        tide.transfer(bob, 1_000_000e18);
        tide.transfer(carol, 1_000_000e18);
        vm.stopPrank();

        for (uint256 i = 0; i < 3; ++i) {
            address holder = [alice, bob, carol][i];
            vm.prank(holder);
            tide.approve(address(escrow), type(uint256).max);
        }
    }

    function _lock(address who, uint256 amount, uint256 duration) internal {
        vm.prank(who);
        escrow.createLock(amount, block.timestamp + duration);
    }

    function _grantProposal(address to, uint256 amount, string memory description)
        internal
        view
        returns (address[] memory targets, uint256[] memory values, bytes[] memory calldatas, bytes32 descriptionHash)
    {
        targets = new address[](1);
        values = new uint256[](1);
        calldatas = new bytes[](1);
        targets[0] = address(tide);
        calldatas[0] = abi.encodeCall(TideToken.transfer, (to, amount));
        descriptionHash = keccak256(bytes(description));
    }
}
