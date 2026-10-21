pragma solidity 0.8.30;
import {Test} from "forge-std/Test.sol";
import {stdJson} from "forge-std/StdJson.sol";
contract TransferCheck is Test {
    using stdJson for string;
    address recipient;
    function setUp() public {
        string memory chain = vm.readFile("chain.json");
        recipient = chain.readAddress(".recipient");
        vm.createSelectFork("chain");
    }
    function test_recipient_balance() public view {
        assertEq(recipient.balance, 2 ether, "recipient holds the requested ether");
    }
}
