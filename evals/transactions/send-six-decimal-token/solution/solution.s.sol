// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {Script} from "forge-std/Script.sol";
import {stdJson} from "forge-std/StdJson.sol";
import {IERC20} from "forge-std/interfaces/IERC20.sol";

contract Solution is Script {
    using stdJson for string;

    function run() external {
        string memory chain = vm.readFile("chain.json");
        IERC20 token = IERC20(chain.readAddress(".token"));
        uint256 amount = 125 * 10 ** token.decimals() / 10;
        vm.startBroadcast(uint256(chain.readBytes32(".privateKey")));
        token.transfer(chain.readAddress(".recipient"), amount);
        vm.stopBroadcast();
    }
}
