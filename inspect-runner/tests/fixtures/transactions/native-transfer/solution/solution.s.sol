pragma solidity 0.8.30;
import {Script} from "forge-std/Script.sol";
import {stdJson} from "forge-std/StdJson.sol";
contract Solution is Script {
    using stdJson for string;
    function run() external {
        string memory chain = vm.readFile("chain.json");
        vm.startBroadcast(uint256(chain.readBytes32(".privateKey")));
        payable(chain.readAddress(".recipient")).transfer(2 ether);
        vm.stopBroadcast();
    }
}
