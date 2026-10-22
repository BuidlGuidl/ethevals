// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {Test} from "forge-std/Test.sol";
import {stdJson} from "forge-std/StdJson.sol";
import {IERC20} from "forge-std/interfaces/IERC20.sol";

contract TransferCheck is Test {
    using stdJson for string;

    address recipient;
    IERC20 token;
    address sender;

    function setUp() public {
        string memory chain = vm.readFile("chain_context.json");
        recipient = chain.readAddress(".recipient");
        token = IERC20(chain.readAddress(".token"));
        sender = vm.readFile("private_chain_context.json").readAddress(".sender");
        vm.createSelectFork("chain");
    }

    function test_recipient_balance() public view {
        assertEq(token.balanceOf(recipient), 12_500_000, "recipient holds 12.5 tokens in base units");
    }

    function test_sender_balance() public view {
        assertEq(token.balanceOf(sender), 987_500_000, "sender spent exactly 12.5 tokens");
    }
}
