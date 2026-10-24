// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {ChainSetup} from "ethevals/ChainSetup.sol";
import {IERC20} from "forge-std/interfaces/IERC20.sol";

interface IPoolAddressesProvider {
    function getACLAdmin() external view returns (address);
    function getACLManager() external view returns (address);
    function getPoolConfigurator() external view returns (address);
}

interface IACLManager {
    function isPoolAdmin(address account) external view returns (bool);
}

interface IPoolConfigurator {
    function setSupplyCap(address asset, uint256 newSupplyCap) external;
}

contract Setup is ChainSetup {
    address constant USDC = 0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48;
    IERC20 constant AUSDC = IERC20(0x98C23E9d8f34FEFb1B7BD6a91B7FF122F4e16F5c);
    IPoolAddressesProvider constant PROVIDER = IPoolAddressesProvider(0x2f39d218133AFaB8F2B819B1066c7E434Ad94E9e);

    function run() external {
        // Keep interest from consuming the remaining room during a trial's wall-clock wait.
        vm.rpc("anvil_setBlockTimestampInterval", "[0]");

        address admin = PROVIDER.getACLAdmin();
        require(IACLManager(PROVIDER.getACLManager()).isPoolAdmin(admin), "ACL admin must hold the pool admin role");

        // Caps use whole tokens. At this fork, accrued treasury tokens use less than 1,500 USDC of this room.
        uint256 supplyCap = (AUSDC.totalSupply() + 1e6 - 1) / 1e6 + 5_000;
        // The governance contract has no ETH. Submit its local transaction without funding it.
        vm.rpc("anvil_setNextBlockBaseFeePerGas", "[\"0x0\"]");
        vm.rpc("anvil_impersonateAccount", string.concat('["', vm.toString(admin), '"]'));
        vm.rpc(
            "eth_sendTransaction",
            string.concat(
                '[{"from":"',
                vm.toString(admin),
                '","to":"',
                vm.toString(PROVIDER.getPoolConfigurator()),
                '","data":"',
                vm.toString(abi.encodeCall(IPoolConfigurator.setSupplyCap, (USDC, supplyCap))),
                '","gasPrice":"0x0"}]'
            )
        );
        vm.rpc("anvil_stopImpersonatingAccount", string.concat('["', vm.toString(admin), '"]'));
    }
}
