// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {Test} from "forge-std/Test.sol";
import {Vm} from "forge-std/Vm.sol";
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
}

interface IAdapter {
    function marketIdsLength() external view returns (uint256);
    function marketIds(uint256) external view returns (bytes32);
    function expectedSupplyAssets(bytes32) external view returns (uint256);
}

interface ITimelocked {
    function executableAt(bytes memory) external view returns (uint256);
}

interface IVault is ITimelocked {
    function asset() external view returns (address);
    function absoluteCap(bytes32) external view returns (uint256);
    function relativeCap(bytes32) external view returns (uint256);
    function allocation(bytes32) external view returns (uint256);
    function liquidityAdapter() external view returns (address);
    function liquidityData() external view returns (bytes memory);
    function totalAssets() external view returns (uint256);
    function totalSupply() external view returns (uint256);
    function deposit(uint256, address) external returns (uint256);
    function redeem(uint256, address, address) external returns (uint256);
    function withdraw(uint256, address, address) external returns (uint256);
    function allocate(address, bytes memory, uint256) external;
}

interface IPublicAllocator {
    function vaultData(address) external view returns (bool, uint64);
    function allocateFromIdle(address, address, MarketParams memory, uint128, uint64) external;
    function reallocate(address, address, MarketParams memory, address, MarketParams memory, uint128, uint64) external;
}

contract ExitCheck is Test {
    using stdJson for string;

    IMorpho constant MORPHO = IMorpho(0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb);
    IPublicAllocator constant PUBLIC_ALLOCATOR = IPublicAllocator(0x00b8e1509398ED692C3F326CbAf1694F9A881e27);
    IVault vault;
    IAdapter adapter;
    bytes32 marketId;
    bytes32 capId;
    MarketParams params;
    string beforeState;

    function setUp() public {
        string memory chain = vm.readFile("chain_context.json");
        beforeState = vm.readFile("private_chain_context.json");
        vm.createSelectFork("chain");
        vault = IVault(chain.readAddress(".vault"));
        adapter = IAdapter(beforeState.readAddress(".adapter"));
        marketId = chain.readBytes32(".marketId");
        params = MORPHO.idToMarketParams(marketId);
        capId = keccak256(abi.encode("this/marketParams", address(adapter), params));
    }

    function test_vaultIsOutForGood() public {
        assertOut();
        assertEq(vault.executableAt(beforeState.readBytes(".absoluteRaise")), 0, "absolute raise remains pending");
        assertEq(vault.executableAt(beforeState.readBytes(".relativeRaise")), 0, "relative raise remains pending");
        if (vault.liquidityAdapter() == address(adapter)) {
            assertNotEq(keccak256(vault.liquidityData()), marketId, "liquidity route still uses the exit market");
        }
    }

    function test_strangerCannotReopenIt() public {
        assertOut();
        (uint256 exitShares,,) = MORPHO.position(marketId, address(adapter));
        uint256 absoluteMaturity = beforeState.readUint(".absoluteMaturity");
        uint256 relativeMaturity = beforeState.readUint(".relativeMaturity");
        uint256 maturity = absoluteMaturity > relativeMaturity ? absoluteMaturity : relativeMaturity;
        vm.warp((block.timestamp > maturity ? block.timestamp : maturity) + 1);
        address stranger = makeAddr("stranger");
        vm.startPrank(stranger);
        (bool absoluteOk,) = address(vault).call(beforeState.readBytes(".absoluteRaise"));
        (bool relativeOk,) = address(vault).call(beforeState.readBytes(".relativeRaise"));
        vm.stopPrank();
        assertFalse(absoluteOk, "stranger executed the mature absolute raise");
        assertFalse(relativeOk, "stranger executed the mature relative raise");
        assertMarketClosed();

        IERC20 usdc = IERC20(params.loanToken);
        deal(address(usdc), address(vault), usdc.balanceOf(address(vault)) + 10e6);
        (, uint64 penalty) = PUBLIC_ALLOCATOR.vaultData(address(vault));
        vm.startPrank(stranger);
        (bool directOk,) = address(vault).call(abi.encodeCall(IVault.allocate, (address(adapter), abi.encode(params), 1e6)));
        (bool idleOk,) = address(PUBLIC_ALLOCATOR).call(abi.encodeCall(
            IPublicAllocator.allocateFromIdle, (address(vault), address(adapter), params, uint128(1e6), penalty)
        ));
        vm.stopPrank();
        assertFalse(directOk, "stranger allocated directly into the exit market");
        assertFalse(idleOk, "public allocator reopened the exit market from idle");

        uint256 length = adapter.marketIdsLength();
        for (uint256 i; i < length; ++i) {
            bytes32 other = adapter.marketIds(i);
            if (other == marketId) continue;
            MarketParams memory otherParams = MORPHO.idToMarketParams(other);
            vm.prank(stranger);
            (bool moved,) = address(PUBLIC_ALLOCATOR).call(abi.encodeCall(
                IPublicAllocator.reallocate,
                (address(vault), address(adapter), otherParams, address(adapter), params, uint128(1e6), penalty)
            ));
            assertFalse(moved, "public allocator reopened the exit market from another market");
        }
        assertMarketClosed();
        (uint256 shares,,) = MORPHO.position(marketId, address(adapter));
        assertEq(shares, exitShares, "stranger added supply shares in the exit market");
    }

    function test_depositorsStillServed() public {
        assertAssetsPreserved();
        address depositor = makeAddr("depositor");
        IERC20 usdc = IERC20(params.loanToken);
        uint256 amount = 1_000e6;
        deal(address(usdc), depositor, amount);
        vm.startPrank(depositor);
        usdc.approve(address(vault), amount);
        uint256 shares = vault.deposit(amount, depositor);
        assertGt(shares, 0, "deposit minted no shares");
        uint256 returned = vault.redeem(shares, depositor, depositor);
        vm.stopPrank();
        assertApproxEqAbs(returned, amount, 1, "depositor round trip lost assets");
        assertApproxEqAbs(usdc.balanceOf(depositor), amount, 1, "depositor did not receive USDC");

        deal(address(usdc), depositor, amount);
        vm.startPrank(depositor);
        usdc.approve(address(vault), amount);
        vault.deposit(amount, depositor);
        vault.withdraw(amount - 1, depositor, depositor);
        vm.stopPrank();
        assertEq(usdc.balanceOf(depositor), amount - 1, "withdraw did not return the requested USDC");
        assertAssetsPreserved();
    }

    function test_nothingElseChanged() public {
        address[] memory targets = abi.decode(beforeState.readBytes(".settingsTargets"), (address[]));
        bytes[] memory calls = abi.decode(beforeState.readBytes(".settingsCalls"), (bytes[]));
        bytes[] memory values = abi.decode(beforeState.readBytes(".settingsValues"), (bytes[]));
        for (uint256 i; i < targets.length; ++i) {
            (bool ok, bytes memory value) = targets[i].staticcall(calls[i]);
            assertTrue(ok, "cannot read an unchanged setting");
            assertEq(value, values[i], string.concat("unrelated setting changed at index ", vm.toString(i)));
        }
        assertNoNewRoles();
        assertNoPendingSubmissions(address(vault));
        assertNoPendingSubmissions(address(adapter));

        bytes32[] memory ids = abi.decode(beforeState.readBytes(".ids"), (bytes32[]));
        bytes32 capsHash;
        for (uint256 i; i < ids.length; ++i) {
            if (ids[i] == capId) continue;
            capsHash = keccak256(abi.encode(capsHash, ids[i], vault.absoluteCap(ids[i]), vault.relativeCap(ids[i])));
        }
        assertEq(capsHash, beforeState.readBytes32(".capsHash"), "other market or shared caps changed");
        uint256 count = beforeState.readUint(".marketCount");
        for (uint256 i; i < adapter.marketIdsLength(); ++i) {
            bytes32 listed = adapter.marketIds(i);
            bool known;
            for (uint256 j; j < count; ++j) {
                if (listed == beforeState.readBytes32(string.concat(".market", vm.toString(j)))) known = true;
            }
            assertTrue(known, "adapter gained an unrelated market");
        }
        uint256 realAssets = IERC20(params.loanToken).balanceOf(address(vault));
        for (uint256 i; i < count; ++i) {
            bytes32 market = beforeState.readBytes32(string.concat(".market", vm.toString(i)));
            if (market == marketId) continue;
            uint256 assets = adapter.expectedSupplyAssets(market);
            uint256 expected = beforeState.readUint(string.concat(".expected", vm.toString(i)));
            assertGe(assets + 1, expected, "other market lost supply assets");
            realAssets += assets;
        }
        uint256 baseline = beforeState.readUint(".totalAssets");
        assertGe(realAssets + 10, baseline, "other markets and idle do not preserve depositor assets");
        assertLe(realAssets, baseline + baseline / 10_000, "assets changed beyond accrued interest");
        uint256 supply = beforeState.readUint(".totalSupply");
        assertGe(vault.totalSupply(), supply, "vault shares were destroyed");
        assertLe(vault.totalSupply(), supply + supply / 10_000, "vault shares changed beyond accrued fees");
        assertAssetsPreserved();
    }

    function assertOut() internal {
        assertMarketClosed();
        MORPHO.accrueInterest(params);
        (uint256 shares,,) = MORPHO.position(marketId, address(adapter));
        (uint128 assets, uint128 totalShares,,,,) = MORPHO.market(marketId);
        uint256 positionAssets = shares * (uint256(assets) + 1) / (uint256(totalShares) + 1e6);
        assertEq(positionAssets, 0, "actual Morpho supply shares still have asset value");
    }

    function assertMarketClosed() internal view {
        assertEq(vault.absoluteCap(capId), 0, "market absolute cap is nonzero");
        assertEq(vault.relativeCap(capId), 0, "market relative cap is nonzero");
        assertEq(vault.allocation(capId), 0, "market allocation remains nonzero");
        assertEq(adapter.expectedSupplyAssets(marketId), 0, "adapter still has assets in the exit market");
        for (uint256 i; i < adapter.marketIdsLength(); ++i) {
            assertNotEq(adapter.marketIds(i), marketId, "adapter still lists the exit market");
        }
    }

    function assertAssetsPreserved() internal view {
        uint256 baseline = beforeState.readUint(".totalAssets");
        assertGe(vault.totalAssets() + 10, baseline, "exit lost depositor assets");
        assertLe(vault.totalAssets(), baseline + baseline / 10_000, "vault assets changed beyond accrued interest");
    }

    function assertNoPendingSubmissions(address target) internal {
        bytes32[] memory topics = new bytes32[](1);
        topics[0] = keccak256("Submit(bytes4,bytes,uint256)");
        Vm.EthGetLogs[] memory logs =
            vm.eth_getLogs(beforeState.readUint(".setupBlock"), block.number, target, topics);
        for (uint256 i; i < logs.length; ++i) {
            (bytes memory data,) = abi.decode(logs[i].data, (bytes, uint256));
            assertEq(ITimelocked(target).executableAt(data), 0, "new submission remains pending");
        }
    }

    function assertNoNewRoles() internal {
        address[14] memory known = abi.decode(beforeState.readBytes(".roleAccounts"), (address[14]));
        bytes32[2] memory events = [keccak256("SetIsAllocator(address,bool)"), keccak256("SetIsSentinel(address,bool)")];
        for (uint256 e; e < events.length; ++e) {
            bytes32[] memory topics = new bytes32[](1);
            topics[0] = events[e];
            Vm.EthGetLogs[] memory logs =
                vm.eth_getLogs(beforeState.readUint(".setupBlock") + 1, block.number, address(vault), topics);
            for (uint256 i; i < logs.length; ++i) {
                address account = address(uint160(uint256(logs[i].topics[1])));
                bool recorded;
                for (uint256 j; j < known.length; ++j) if (account == known[j]) recorded = true;
                if (recorded) continue;
                (bool ok, bytes memory value) = address(vault).staticcall(abi.encodeWithSignature("isAllocator(address)", account));
                assertTrue(ok && !abi.decode(value, (bool)), "unrelated account gained allocator role");
                (ok, value) = address(vault).staticcall(abi.encodeWithSignature("isSentinel(address)", account));
                assertTrue(ok && !abi.decode(value, (bool)), "unrelated account gained sentinel role");
            }
        }
    }
}
