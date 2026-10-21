// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;
import {Test} from "forge-std/Test.sol";
import {Counter} from "workspace/src/Counter.sol";
contract CounterTest is Test {
    function test_value() public {
        assertEq(new Counter().value(), 7, "counter value");
    }
}
