// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {Script} from "forge-std/Script.sol";
import {TimelockController} from "@openzeppelin/contracts/governance/TimelockController.sol";
import {TransparentUpgradeableProxy} from "@openzeppelin/contracts/proxy/transparent/TransparentUpgradeableProxy.sol";
import {Staking} from "../src/Staking.sol";
import {Token} from "../src/Token.sol";
import {Treasury} from "../src/Treasury.sol";

contract Deploy is Script {
    uint256 constant TIMELOCK_DELAY = 2 days;
    uint256 constant INITIAL_SUPPLY = 5_080_000 ether;
    uint256 constant TREASURY_SUPPLY = 5_000_000 ether;
    /// TOKEN minted to stakers per second.
    uint256 constant REWARD_RATE = 0.05 ether;

    function run() external returns (TimelockController timelock, Token token, Staking staking, Treasury treasury) {
        uint256 deployerKey = vm.envUint("DEPLOYER_PRIVATE_KEY");
        address deployer = vm.addr(deployerKey);

        vm.startBroadcast(deployerKey);
        // The deployer proposes, and anyone can execute once the delay has passed.
        address[] memory proposers = new address[](1);
        proposers[0] = deployer;
        address[] memory executors = new address[](1);
        executors[0] = address(0);
        timelock = new TimelockController(TIMELOCK_DELAY, proposers, executors, deployer);

        token = new Token(deployer, INITIAL_SUPPLY);
        bytes memory init = abi.encodeCall(Staking.initialize, (token, deployer, REWARD_RATE));
        staking = Staking(address(new TransparentUpgradeableProxy(address(new Staking()), address(timelock), init)));
        treasury = new Treasury(address(timelock));
        token.transfer(address(treasury), TREASURY_SUPPLY);

        // Upgrades, the treasury and the token's roles all sit behind the timelock.
        token.grantRole(token.MINTER_ROLE(), address(staking));
        token.grantRole(token.PAUSER_ROLE(), vm.envAddress("GUARDIAN"));
        token.grantRole(token.DEFAULT_ADMIN_ROLE(), address(timelock));
        token.renounceRole(token.DEFAULT_ADMIN_ROLE(), deployer);
        vm.stopBroadcast();
    }
}
