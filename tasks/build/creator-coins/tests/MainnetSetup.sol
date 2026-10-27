// SPDX-License-Identifier: GPL-2.0-or-later
pragma solidity 0.8.30;

import {Test} from "forge-std/Test.sol";
import {MainnetCode} from "./MainnetCode.sol";

interface TestToken {
    function balanceOf(address) external view returns (uint256);
    function totalSupply() external view returns (uint256);
    function decimals() external view returns (uint8);
    function approve(address, uint256) external returns (bool);
    function transfer(address, uint256) external returns (bool);
    function transferFrom(address, address, uint256) external returns (bool);
    function deposit() external payable;
}

interface TestFactory {
    function createPool(address, address, uint24) external returns (address);
    function getPool(address, address, uint24) external view returns (address);
    function feeAmountTickSpacing(uint24) external view returns (int24);
    function owner() external view returns (address);
}

interface TestPool {
    function token0() external view returns (address);
    function token1() external view returns (address);
    function fee() external view returns (uint24);
    function tickSpacing() external view returns (int24);
    function liquidity() external view returns (uint128);
    function initialize(uint160) external;
    function slot0() external view returns (uint160, int24, uint16, uint16, uint16, uint8, bool);
    function swap(address, bool, int256, uint160, bytes calldata) external returns (int256, int256);
}

abstract contract MainnetSetup is Test {
    address internal constant FACTORY = 0x1F98431c8aD98523631AE4a59f267346ea31F984;
    address internal constant MANAGER = 0xC36442b4a4522E871399CD717aBDD847Ab11FE88;
    address internal constant ROUTER = 0xE592427A0AEce92De3Edee1F18E0157C05861564;
    address internal constant ROUTER02 = 0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45;
    address internal constant WETH = 0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2;
    address internal constant GOVERNANCE = 0xf2371551Fe3937Db7c750f4DfABe5c2fFFdcBf5A;
    uint160 internal constant MIN_PRICE = 4295128740;
    uint160 internal constant MAX_PRICE = 1461446703485210103287273052203988822378723970341;

    function installMainnet() internal {
        vm.chainId(1);
        vm.etch(FACTORY, MainnetCode.factory());
        vm.etch(MANAGER, MainnetCode.manager());
        vm.etch(ROUTER, MainnetCode.router());
        vm.etch(ROUTER02, MainnetCode.router02());
        vm.etch(WETH, MainnetCode.weth());
        // Factory constructor state and fee tiers enabled through block 26264728.
        vm.store(FACTORY, bytes32(uint256(3)), bytes32(uint256(uint160(GOVERNANCE))));
        setFee(100, 1);
        setFee(500, 10);
        setFee(3000, 60);
        setFee(10000, 200);
        // OZ ERC721 stores its names at slots 6 and 7. Both counters share slot 13.
        vm.store(MANAGER, bytes32(uint256(6)), bytes32(uint256(bytes32("Uniswap V3 Positions NFT-V1")) | 54));
        vm.store(MANAGER, bytes32(uint256(7)), bytes32(uint256(bytes32("UNI-V3-POS")) | 20));
        vm.store(MANAGER, bytes32(uint256(13)), bytes32((uint256(1) << 176) | 1));
        bytes4[4] memory interfaces = [bytes4(0x01ffc9a7), bytes4(0x80ac58cd), bytes4(0x5b5e139f), bytes4(0x780e9d63)];
        for (uint256 i; i < interfaces.length; ++i) {
            vm.store(MANAGER, keccak256(abi.encode(interfaces[i], uint256(0))), bytes32(uint256(1)));
        }
        vm.store(WETH, bytes32(uint256(0)), bytes32(uint256(bytes32("Wrapped Ether")) | 26));
        vm.store(WETH, bytes32(uint256(1)), bytes32(uint256(bytes32("WETH")) | 8));
        vm.store(WETH, bytes32(uint256(2)), bytes32(uint256(18)));
    }

    function setFee(uint24 fee, int24 spacing) private {
        vm.store(FACTORY, keccak256(abi.encode(fee, uint256(4))), bytes32(uint256(uint24(spacing))));
    }
}
