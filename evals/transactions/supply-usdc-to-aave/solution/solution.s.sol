// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {Script} from "forge-std/Script.sol";
import {stdJson} from "forge-std/StdJson.sol";
import {IERC20} from "forge-std/interfaces/IERC20.sol";

interface IPool {
    function supply(address asset, uint256 amount, address onBehalfOf, uint16 referralCode) external;
}

contract Solution is Script {
    using stdJson for string;

    address constant USDC = 0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48;
    address constant POOL = 0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2;

    function run() external {
        string memory chain = vm.readFile("chain.json");
        uint256 privateKey = uint256(chain.readBytes32(".privateKey"));
        address me = vm.addr(privateKey);
        vm.startBroadcast(privateKey);
        IERC20(USDC).approve(POOL, 10_000e6);
        IPool(POOL).supply(USDC, 10_000e6, me, 0);
        vm.stopBroadcast();
    }
}
