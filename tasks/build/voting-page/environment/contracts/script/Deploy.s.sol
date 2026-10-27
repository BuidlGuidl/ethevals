// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {Script} from "forge-std/Script.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {TimelockController} from "@openzeppelin/contracts/governance/TimelockController.sol";
import {VoteToken} from "../src/VoteToken.sol";
import {TokenGovernor} from "../src/TokenGovernor.sol";

contract Deploy is Script {
    function run(address token) external returns (address governorAddress, address holder) {
        vm.startBroadcast();
        (, address broadcaster,) = vm.readCallers();
        VoteToken votes = new VoteToken(IERC20(token));
        address[] memory proposers = new address[](0);
        address[] memory executors = new address[](1);
        executors[0] = address(0);
        TimelockController timelock = new TimelockController(2 days, proposers, executors, broadcaster);
        TokenGovernor governor = new TokenGovernor(votes, IERC20(token), timelock);
        timelock.grantRole(timelock.PROPOSER_ROLE(), address(governor));
        timelock.grantRole(timelock.CANCELLER_ROLE(), address(governor));
        timelock.renounceRole(timelock.DEFAULT_ADMIN_ROLE(), broadcaster);
        vm.stopBroadcast();
        return (address(governor), address(timelock));
    }
}
