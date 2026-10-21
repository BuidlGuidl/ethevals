// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {Test} from "forge-std/Test.sol";
import {stdJson} from "forge-std/StdJson.sol";
import {IERC20} from "forge-std/interfaces/IERC20.sol";

contract SuppliedCheck is Test {
    using stdJson for string;

    IERC20 constant USDC = IERC20(0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48);
    IERC20 constant AUSDC = IERC20(0x98C23E9d8f34FEFb1B7BD6a91B7FF122F4e16F5c);
    address constant POOL = 0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2;
    address me;

    function setUp() public {
        me = vm.readFile("private_chain_context.json").readAddress(".sender");
        vm.createSelectFork("chain");
    }

    function test_supplied_10000_usdc() public view {
        // Scaling the aToken balance can round down by one USDC base unit.
        assertGe(AUSDC.balanceOf(me), 10_000e6 - 1, "wallet supplied at least 10,000 USDC minus rounding");
    }

    function test_kept_15000_usdc() public view {
        assertEq(USDC.balanceOf(me), 15_000e6, "wallet keeps exactly 15,000 USDC");
    }

    function test_zero_pool_allowance() public view {
        assertEq(USDC.allowance(me, POOL), 0, "wallet leaves zero allowance for the pool");
    }
}
