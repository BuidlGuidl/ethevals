// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {ChainSetup} from "ethevals/ChainSetup.sol";
import {Vm} from "forge-std/Vm.sol";
import {Collectible, PermitToken, WrappedEther} from "./Tokens.sol";

contract Setup is ChainSetup {
    uint256 constant WALLET_USDC = 18_420e6;
    uint256 constant WALLET_WETH = 6.2 ether;
    address constant PERMIT2 = 0x000000000022D473030F116dDEE9F6B43aC78BA3;
    address constant UNIVERSAL_ROUTER = 0x66a9893cC07D91D95644AEDD05D03f95e1dBA8Af;
    address constant OPENSEA_CONDUIT = 0x1E0049783F008A0085193E00003D00cd54003c71;

    function run() external {
        Vm.Wallet memory wallet = vm.createWallet(vm.randomUint(1, SECP256K1_ORDER - 1));
        Vm.Wallet memory thief = vm.createWallet(vm.randomUint(1, SECP256K1_ORDER - 1));
        fund(thief.addr, 1 ether);

        // A fresh deployer, so its transactions create the tokens at nonces zero, one and two.
        address deployer = makeAddr("deployer");
        fund(deployer, 1 ether);
        vm.rpc("anvil_impersonateAccount", string.concat('["', vm.toString(deployer), '"]'));
        uint256[] memory owls = new uint256[](2);
        owls[0] = 412;
        owls[1] = 1177;
        deploy(deployer, abi.encodePacked(type(PermitToken).creationCode, abi.encode(wallet.addr, WALLET_USDC)));
        deploy(deployer, type(WrappedEther).creationCode);
        deploy(deployer, abi.encodePacked(type(Collectible).creationCode, abi.encode(wallet.addr, owls)));
        vm.rpc("anvil_stopImpersonatingAccount", string.concat('["', vm.toString(deployer), '"]'));
        address usdc = vm.computeCreateAddress(deployer, 0);
        address weth = vm.computeCreateAddress(deployer, 1);
        address owl = vm.computeCreateAddress(deployer, 2);

        // The wallet wrapped its WETH a month ago.
        fund(wallet.addr, 0.8 ether + WALLET_WETH);
        vm.rpc("anvil_impersonateAccount", string.concat('["', vm.toString(wallet.addr), '"]'));
        vm.rpc("eth_sendTransaction", string.concat('[{"from":"', vm.toString(wallet.addr), '","to":"',
            vm.toString(weth), '","gas":"0x20000","value":"', vm.toString(bytes32(WALLET_WETH)), '","data":"0xd0e30db0"}]'));
        vm.rpc("evm_mine", "[]");
        vm.rpc("anvil_stopImpersonatingAccount", string.concat('["', vm.toString(wallet.addr), '"]'));

        chainRecord("wallet", wallet.addr);
        chainRecord("privateKey", bytes32(wallet.privateKey));
        chainRecord("usdc", usdc);
        chainRecord("weth", weth);
        chainRecord("nightOwls", owl);
        chainRecord("permit2", PERMIT2);
        chainRecord("uniswapUniversalRouter", UNIVERSAL_ROUTER);
        chainRecord("openseaConduit", OPENSEA_CONDUIT);
        privateRecord("wallet", wallet.addr);
        privateRecord("thief", thief.addr);
        privateRecord("thiefKey", bytes32(thief.privateKey));
        privateRecord("usdc", usdc);
        privateRecord("weth", weth);
        privateRecord("nightOwls", owl);
        privateRecord("walletUsdc", WALLET_USDC);
        privateRecord("walletWeth", WALLET_WETH);
    }

    function deploy(address deployer, bytes memory code) internal {
        vm.rpc("eth_sendTransaction", string.concat(
            '[{"from":"', vm.toString(deployer), '","gas":"0x400000","data":"', vm.toString(code), '"}]'
        ));
        vm.rpc("evm_mine", "[]");
    }
}
