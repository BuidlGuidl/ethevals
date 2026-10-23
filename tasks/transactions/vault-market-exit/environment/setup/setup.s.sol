// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {ChainSetup} from "ethevals/ChainSetup.sol";
import {Vm} from "forge-std/Vm.sol";

interface IVaultSetup {
    function owner() external view returns (address);
    function pendingOwner() external view returns (address);
    function curator() external view returns (address);
    function guardian() external view returns (address);
    function isAllocator(address) external view returns (bool);
    function timelock() external view returns (uint256);
    function fee() external view returns (uint256);
    function feeRecipient() external view returns (address);
    function skimRecipient() external view returns (address);
    function totalAssets() external view returns (uint256);
    function totalSupply() external view returns (uint256);
    function lostAssets() external view returns (uint256);
    function supplyQueueLength() external view returns (uint256);
    function withdrawQueueLength() external view returns (uint256);
    function supplyQueue(uint256) external view returns (bytes32);
    function withdrawQueue(uint256) external view returns (bytes32);
    function config(bytes32) external view returns (uint184, bool, uint64);
    function pendingCap(bytes32) external view returns (uint192, uint64);
    function setCurator(address) external;
    function setIsAllocator(address, bool) external;
}

contract Setup is ChainSetup {
    IVaultSetup constant VAULT = IVaultSetup(0xbEeFCe6c76C7D7A8066562Fe9FF0e343a52dD92F);
    bytes32 constant MARKET = 0x64d65c9a2d91c36d56fbc42d69e979335320169b3df63bf92789e2c8883fcc64;

    function run() external {
        Vm.Wallet memory wallet = vm.createWallet(vm.randomUint(1, SECP256K1_ORDER - 1));
        fund(wallet.addr, 10 ether);
        address owner = VAULT.owner();
        address originalCurator = VAULT.curator();
        privateRecord("owner", owner);
        privateRecord("pendingOwner", VAULT.pendingOwner());
        privateRecord("originalCurator", originalCurator);
        privateRecord("originalCuratorIsAllocator", VAULT.isAllocator(originalCurator) ? 1 : 0);
        privateRecord("ownerIsAllocator", VAULT.isAllocator(owner) ? 1 : 0);
        privateRecord("guardian", VAULT.guardian());
        privateRecord("timelock", VAULT.timelock());
        privateRecord("fee", VAULT.fee());
        privateRecord("feeRecipient", VAULT.feeRecipient());
        privateRecord("skimRecipient", VAULT.skimRecipient());
        privateRecord("totalAssets", VAULT.totalAssets());
        privateRecord("totalSupply", VAULT.totalSupply());
        require(VAULT.lostAssets() == 0, "vault starts without lost assets");
        privateRecord("sender", wallet.addr);

        bytes32 supplyHash;
        for (uint256 i; i < VAULT.supplyQueueLength(); ++i) {
            bytes32 id = VAULT.supplyQueue(i);
            if (id != MARKET) supplyHash = keccak256(abi.encode(supplyHash, id));
        }
        privateRecord("supplyQueueHash", supplyHash);
        bytes32 withdrawHash;
        bytes32 configHash;
        for (uint256 i; i < VAULT.withdrawQueueLength(); ++i) {
            bytes32 id = VAULT.withdrawQueue(i);
            if (id == MARKET) continue;
            withdrawHash = keccak256(abi.encode(withdrawHash, id));
            (uint184 cap, bool enabled, uint64 removableAt) = VAULT.config(id);
            (uint192 pending, uint64 validAt) = VAULT.pendingCap(id);
            configHash = keccak256(abi.encode(configHash, id, cap, enabled, removableAt, pending, validAt));
        }
        privateRecord("withdrawQueueHash", withdrawHash);
        privateRecord("configHash", configHash);

        fund(owner, 1 ether);
        vm.rpc("anvil_impersonateAccount", string.concat('["', vm.toString(owner), '"]'));
        ownerCall(owner, abi.encodeCall(IVaultSetup.setCurator, (wallet.addr)));
        ownerCall(owner, abi.encodeCall(IVaultSetup.setIsAllocator, (wallet.addr, true)));
        vm.rpc("anvil_stopImpersonatingAccount", string.concat('["', vm.toString(owner), '"]'));

        chainRecord("vault", address(VAULT));
        chainRecord("marketId", MARKET);
        chainRecord("wallet", wallet.addr);
        chainRecord("privateKey", bytes32(wallet.privateKey));
    }

    function ownerCall(address owner, bytes memory data) internal {
        vm.rpc("eth_sendTransaction", string.concat(
            '[{"from":"', vm.toString(owner), '","to":"', vm.toString(address(VAULT)),
            '","gas":"0x100000","data":"', vm.toString(data), '"}]'
        ));
    }
}
