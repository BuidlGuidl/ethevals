// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {ChainSetup} from "ethevals/ChainSetup.sol";

contract Setup is ChainSetup {
    function run() external {
        address treasury = address(uint160(vm.randomUint(1, type(uint160).max)));
        require(treasury.code.length == 0, "Treasury must have no code");
        chainRecord("treasury", treasury);
        privateRecord("treasury", treasury);
    }
}
