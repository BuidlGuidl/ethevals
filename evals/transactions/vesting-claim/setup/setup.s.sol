// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {ChainSetup} from "ethevals/ChainSetup.sol";
import {Vm} from "forge-std/Vm.sol";
import {IERC20} from "forge-std/interfaces/IERC20.sol";
import {Vesting} from "../workspace/src/Vesting.sol";

contract Setup is ChainSetup {
    address constant USDC = 0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48;
    address constant HOLDER = 0x55FE002aefF02F77364de339a1292923A15844B8;

    function run() external {
        Vm.Wallet memory me = vm.createWallet(vm.randomUint(1, SECP256K1_ORDER - 1));
        address beneficiary = vm.randomAddress();
        fund(me.addr, 10 ether);

        vm.startBroadcast(me.privateKey);
        Vesting vesting = new Vesting(beneficiary, uint64(block.timestamp - 730 days), 365 days);
        vm.stopBroadcast();

        vm.rpc("anvil_impersonateAccount", string.concat('["', vm.toString(HOLDER), '"]'));
        // ERC-20 balances can be funded at the future CREATE address before deployment.
        vm.rpc("eth_sendTransaction", string.concat('[{"from":"', vm.toString(HOLDER), '","to":"', vm.toString(USDC),
            '","data":"', vm.toString(abi.encodeCall(IERC20.transfer, (address(vesting), 50_000e6))), '"}]'));
        vm.rpc("anvil_stopImpersonatingAccount", string.concat('["', vm.toString(HOLDER), '"]'));

        chainRecord("privateKey", bytes32(me.privateKey));
        chainRecord("vesting", address(vesting));
        chainRecord("usdc", USDC);
        chainRecord("beneficiary", beneficiary);
    }
}
