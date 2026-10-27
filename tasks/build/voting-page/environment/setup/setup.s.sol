// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {ChainSetup} from "ethevals/ChainSetup.sol";

contract Setup is ChainSetup {
    function run() external {
        vm.rpc("anvil_setBlockTimestampInterval", "[12]");
    }
}
