// SPDX-License-Identifier: MIT
pragma solidity >=0.8.13 <0.9.0;

import {Script} from "forge-std/Script.sol";

abstract contract ChainSetup is Script {
    constructor() {
        vm.serializeString("chain", "rpcUrl", "http://chain:8545");
        vm.writeJson(vm.serializeUint("chain", "chainId", block.chainid), "chain.json");
        vm.writeJson("{}", "private.json");
    }

    function fund(address addr, uint256 amount) internal {
        vm.rpc("anvil_setBalance", string.concat('["', vm.toString(addr), '","', vm.toString(bytes32(amount)), '"]'));
    }

    function chainRecord(string memory name, address value) internal {
        vm.writeJson(vm.serializeAddress("chain", name, value), "chain.json");
    }

    function chainRecord(string memory name, uint256 value) internal {
        vm.writeJson(vm.serializeUint("chain", name, value), "chain.json");
    }

    function chainRecord(string memory name, bytes32 value) internal {
        vm.writeJson(vm.serializeBytes32("chain", name, value), "chain.json");
    }

    function chainRecord(string memory name, string memory value) internal {
        vm.writeJson(vm.serializeString("chain", name, value), "chain.json");
    }

    function privateRecord(string memory name, address value) internal {
        vm.writeJson(vm.serializeAddress("private", name, value), "private.json");
    }

    function privateRecord(string memory name, uint256 value) internal {
        vm.writeJson(vm.serializeUint("private", name, value), "private.json");
    }

    function privateRecord(string memory name, bytes32 value) internal {
        vm.writeJson(vm.serializeBytes32("private", name, value), "private.json");
    }

    function privateRecord(string memory name, string memory value) internal {
        vm.writeJson(vm.serializeString("private", name, value), "private.json");
    }
}
