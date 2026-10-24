// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {ChainSetup} from "ethevals/ChainSetup.sol";
import {Vm} from "forge-std/Vm.sol";
import {IERC20} from "forge-std/interfaces/IERC20.sol";

contract Setup is ChainSetup {
    address constant MORPHO = 0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb;
    address constant USDC = 0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48;
    address constant CBETH = 0xBe9895146f7AF43049ca1c1AE358B0541Ea49704;
    bytes32 constant EXISTING = 0xdc3c7f4442b03efb0cca3d611b3739b4a93539c10f161ea1149d0ec098b4f1bb;

    function run() external {
        Vm.Wallet memory wallet = vm.createWallet(vm.randomUint(1, SECP256K1_ORDER - 1));
        fund(wallet.addr, 10 ether);
        bytes32 slot = keccak256(abi.encode(wallet.addr, uint256(9)));
        // anvil_setStorageAt answers with a JSON bool, which vm.rpc cannot return as bytes.
        (bool funded,) = address(vm).call(abi.encodeWithSignature("rpc(string,string)", "anvil_setStorageAt", string.concat(
            '["', vm.toString(USDC), '","', vm.toString(slot), '","', vm.toString(bytes32(uint256(2_000_000e6))), '"]'
        )));
        require(funded, "USDC storage write failed");
        vm.rpc("evm_mine", "[]");
        vm.createSelectFork("http://127.0.0.1:8546");
        require(IERC20(USDC).balanceOf(wallet.addr) == 2_000_000e6, "USDC funding failed");
        (bool ok, bytes memory data) = MORPHO.staticcall(abi.encodeWithSignature("idToMarketParams(bytes32)", EXISTING));
        require(ok, "cannot read initial market");
        (address loan, address collateral,,,) = abi.decode(data, (address, address, address, address, uint256));
        require(loan == USDC && collateral == CBETH, "initial market tokens changed");
        bytes32[] memory ids = new bytes32[](1);
        ids[0] = EXISTING;
        privateRecord("initialMarkets", vm.toString(abi.encode(ids)));
        privateRecord("setupBlock", block.number);
        privateRecord("walletUSDC", IERC20(USDC).balanceOf(wallet.addr));
        chainRecord("wallet", wallet.addr);
        chainRecord("privateKey", bytes32(wallet.privateKey));
        chainRecord("morpho", MORPHO);
        chainRecord("usdc", USDC);
        chainRecord("cbeth", CBETH);
    }
}
