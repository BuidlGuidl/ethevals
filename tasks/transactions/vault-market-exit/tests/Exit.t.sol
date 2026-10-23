// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {Test} from "forge-std/Test.sol";
import {stdJson} from "forge-std/StdJson.sol";
import {IERC20} from "forge-std/interfaces/IERC20.sol";

struct MarketParams {
    address loanToken;
    address collateralToken;
    address oracle;
    address irm;
    uint256 lltv;
}

interface IMorpho {
    function idToMarketParams(bytes32) external view returns (MarketParams memory);
    function position(bytes32, address) external view returns (uint256, uint128, uint128);
    function market(bytes32) external view returns (uint128, uint128, uint128, uint128, uint128, uint128);
    function accrueInterest(MarketParams memory) external;
    function supply(MarketParams memory, uint256, uint256, address, bytes memory) external returns (uint256, uint256);
}

interface IVault {
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
    function supplyQueueLength() external view returns (uint256);
    function withdrawQueueLength() external view returns (uint256);
    function supplyQueue(uint256) external view returns (bytes32);
    function withdrawQueue(uint256) external view returns (bytes32);
    function config(bytes32) external view returns (uint184, bool, uint64);
    function pendingCap(bytes32) external view returns (uint192, uint64);
}

contract ExitCheck is Test {
    using stdJson for string;

    IMorpho constant MORPHO = IMorpho(0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb);
    IVault vault;
    bytes32 marketId;
    string beforeState;
    address wallet;

    function setUp() public {
        string memory chain = vm.readFile("chain_context.json");
        beforeState = vm.readFile("private_chain_context.json");
        vault = IVault(chain.readAddress(".vault"));
        marketId = chain.readBytes32(".marketId");
        wallet = beforeState.readAddress(".sender");
        vm.createSelectFork("chain");
    }

    function test_vaultIsOutForGood() public {
        (uint256 shares,,) = MORPHO.position(marketId, address(vault));
        assertEq(shares, 0, "vault still supplies to the market");
        (uint184 cap,,) = vault.config(marketId);
        assertEq(cap, 0, "market still has a cap");
        (uint192 pending, uint64 validAt) = vault.pendingCap(marketId);
        assertEq(pending, 0, "market still has a pending cap value");
        assertEq(validAt, 0, "market still has a pending cap");

        bytes32 supplyHash;
        for (uint256 i; i < vault.supplyQueueLength(); ++i) {
            bytes32 id = vault.supplyQueue(i);
            assertNotEq(id, marketId, "market remains on the supply queue");
            supplyHash = keccak256(abi.encode(supplyHash, id));
        }
        assertEq(supplyHash, beforeState.readBytes32(".supplyQueueHash"), "other supply queue entries changed");

        bytes32 withdrawHash;
        bytes32 configHash;
        uint256 realAssets;
        for (uint256 i; i < vault.withdrawQueueLength(); ++i) {
            bytes32 id = vault.withdrawQueue(i);
            assertNotEq(id, marketId, "market remains on the withdraw queue");
            withdrawHash = keccak256(abi.encode(withdrawHash, id));
            (uint184 otherCap, bool enabled, uint64 removableAt) = vault.config(id);
            (uint192 otherPending, uint64 otherValidAt) = vault.pendingCap(id);
            configHash = keccak256(abi.encode(configHash, id, otherCap, enabled, removableAt, otherPending, otherValidAt));
            MORPHO.accrueInterest(MORPHO.idToMarketParams(id));
            (uint256 otherShares,,) = MORPHO.position(id, address(vault));
            (uint128 assets, uint128 totalShares,,,,) = MORPHO.market(id);
            realAssets += otherShares * (uint256(assets) + 1) / (uint256(totalShares) + 1e6);
        }
        assertEq(withdrawHash, beforeState.readBytes32(".withdrawQueueHash"), "other withdraw queue entries changed");
        assertEq(configHash, beforeState.readBytes32(".configHash"), "other market settings changed");
        uint256 baseline = beforeState.readUint(".totalAssets");
        assertGe(vault.totalAssets() + 10, baseline, "exit lost depositor assets");
        assertLe(vault.totalAssets(), baseline + baseline / 10_000, "vault assets changed beyond accrued interest");
        assertGe(realAssets + 10, baseline, "lost assets hide missing depositor funds");
        assertEq(vault.totalSupply(), beforeState.readUint(".totalSupply"), "vault share supply changed");
        assertSettingsUnchanged();
    }

    function test_strangerSupplyOnBehalfChangesNothing() public {
        MarketParams memory params = MORPHO.idToMarketParams(marketId);
        address stranger = makeAddr("stranger");
        uint256 donation = 1_000e6;
        deal(params.loanToken, stranger, donation);
        uint256 assetsBefore = vault.totalAssets();
        (uint256 sharesBefore,,) = MORPHO.position(marketId, address(vault));
        vm.startPrank(stranger);
        IERC20(params.loanToken).approve(address(MORPHO), donation);
        MORPHO.supply(params, donation, 0, address(vault), "");
        vm.stopPrank();
        (uint256 sharesAfter,,) = MORPHO.position(marketId, address(vault));
        assertGt(sharesAfter, sharesBefore, "stranger supply did not reach the vault position");
        assertEq(IERC20(params.loanToken).balanceOf(stranger), 0, "stranger did not supply the tokens");
        assertEq(vault.totalAssets(), assetsBefore, "stranger supply changes vault assets");
    }

    function assertSettingsUnchanged() internal view {
        assertEq(vault.owner(), beforeState.readAddress(".owner"), "owner changed");
        assertEq(vault.pendingOwner(), beforeState.readAddress(".pendingOwner"), "pending owner changed");
        assertEq(vault.guardian(), beforeState.readAddress(".guardian"), "guardian changed");
        assertEq(vault.curator(), wallet, "curator changed");
        assertTrue(vault.isAllocator(wallet), "wallet lost allocator role");
        assertEq(vault.isAllocator(vault.owner()), beforeState.readUint(".ownerIsAllocator") == 1, "owner allocator role changed");
        assertEq(vault.isAllocator(beforeState.readAddress(".originalCurator")), beforeState.readUint(".originalCuratorIsAllocator") == 1, "prior curator allocator role changed");
        assertEq(vault.timelock(), beforeState.readUint(".timelock"), "timelock changed");
        assertEq(vault.fee(), beforeState.readUint(".fee"), "fee changed");
        assertEq(vault.feeRecipient(), beforeState.readAddress(".feeRecipient"), "fee recipient changed");
        assertEq(vault.skimRecipient(), beforeState.readAddress(".skimRecipient"), "skim recipient changed");
    }
}
