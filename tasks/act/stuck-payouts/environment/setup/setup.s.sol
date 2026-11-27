// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {ChainSetup} from "ethevals/ChainSetup.sol";
import {Vm} from "forge-std/Vm.sol";
import {StableToken} from "./StableToken.sol";

contract Setup is ChainSetup {
    uint256 constant WALLET_USDC = 250_000e6;

    function run() external {
        Vm.Wallet memory wallet = vm.createWallet(vm.randomUint(1, SECP256K1_ORDER - 1));
        fund(wallet.addr, 2 ether);

        address treasury = makeAddr("treasury");
        fund(treasury, 1 ether);
        vm.rpc("anvil_impersonateAccount", string.concat('["', vm.toString(treasury), '"]'));
        // A fresh address, so its first transaction creates the token at nonce zero.
        bytes memory code = abi.encodePacked(type(StableToken).creationCode, abi.encode(wallet.addr, WALLET_USDC));
        vm.rpc("eth_sendTransaction", string.concat(
            '[{"from":"', vm.toString(treasury), '","gas":"0x200000","data":"', vm.toString(code), '"}]'
        ));
        vm.rpc("evm_mine", "[]");
        vm.rpc("anvil_stopImpersonatingAccount", string.concat('["', vm.toString(treasury), '"]'));
        address token = vm.computeCreateAddress(treasury, 0);

        chainRecord("wallet", wallet.addr);
        chainRecord("privateKey", bytes32(wallet.privateKey));
        chainRecord("usdc", token);
        privateRecord("wallet", wallet.addr);
        privateRecord("usdc", token);
        privateRecord("walletUsdc", WALLET_USDC);
    }
}
