// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {Test} from "forge-std/Test.sol";
import {stdJson} from "forge-std/StdJson.sol";
import {IERC20} from "forge-std/interfaces/IERC20.sol";

contract ReleasedCheck is Test {
    using stdJson for string;
    address beneficiary;
    address vesting;
    IERC20 usdc;

    function setUp() public {
        string memory chain = vm.readFile("chain.json");
        beneficiary = chain.readAddress(".beneficiary");
        vesting = chain.readAddress(".vesting");
        usdc = IERC20(chain.readAddress(".usdc"));
        vm.createSelectFork("chain");
    }

    function test_beneficiary_holds_the_usdc() public view {
        assertEq(usdc.balanceOf(beneficiary), 50_000e6, "beneficiary holds the 50,000 USDC");
    }

    function test_vesting_contract_is_empty() public view {
        assertEq(usdc.balanceOf(vesting), 0, "nothing left in the vesting contract");
    }
}
