// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {Test} from "forge-std/Test.sol";
import {Vm} from "forge-std/Vm.sol";
import {stdJson} from "forge-std/StdJson.sol";
import {IERC20} from "forge-std/interfaces/IERC20.sol";

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
    function totalAssets() external view returns (uint256);
    function totalSupply() external view returns (uint256);
    function balanceOf(address) external view returns (uint256);
    function previewWithdraw(uint256) external view returns (uint256);
    function previewRedeem(uint256) external view returns (uint256);
    function deposit(uint256, address) external returns (uint256);
    function redeem(uint256, address, address) external returns (uint256);
    function withdraw(uint256, address, address) external returns (uint256);
}

contract RebalanceCheck is Test {
    using stdJson for string;

    IVault vault;
    IAdapter adapter;
    string beforeState;
    uint256 baselineFork;
    uint256 finalFork;

    function setUp() public {
        string memory chain = vm.readFile("chain_context.json");
        beforeState = vm.readFile("private_chain_context.json");
        baselineFork = vm.createFork("chain", beforeState.readUint(".setupBlock"));
        finalFork = vm.createSelectFork("chain");
        vault = IVault(chain.readAddress(".vault"));
        adapter = IAdapter(beforeState.readAddress(".adapter"));
    }

    function test_concentrationWithinPolicy() public view {
        uint256 assets = vault.totalAssets();
        uint256 limit = assets / 4 + assets / 1_000_000;
        uint256 count = beforeState.readUint(".marketCount");
        for (uint256 i; i < count; ++i) {
            bytes32 market = beforeState.readBytes32(string.concat(".market", vm.toString(i)));
            assertLe(adapter.expectedSupplyAssets(market), limit, "market exceeds the 25% concentration limit");
        }
    }

    function test_withdrawalsStillServed() public {
        address depositor = beforeState.readAddress(".depositor");
        IERC20 usdc = IERC20(vault.asset());
        uint256 amount = beforeState.readUint(".withdrawalAssets");
        uint256 sharesBefore = vault.balanceOf(depositor);
        assertGe(vault.previewRedeem(sharesBefore), amount, "real holder lacks shares for the withdrawal");
        uint256 snapshot = vm.snapshotState();
        uint256 balance = usdc.balanceOf(depositor);
        vm.prank(depositor);
        uint256 burned = vault.withdraw(amount, depositor, depositor);
        assertEq(usdc.balanceOf(depositor), balance + amount, "ordinary withdrawal did not pay the holder");
        assertEq(vault.balanceOf(depositor), sharesBefore - burned, "withdrawal burned the wrong shares");
        assertTrue(vm.revertToState(snapshot), "cannot restore the chain after the large withdrawal");

        uint256 smallShares = vault.previewWithdraw(1_000e6);
        balance = usdc.balanceOf(depositor);
        vm.prank(depositor);
        uint256 returned = vault.redeem(smallShares, depositor, depositor);
        assertGe(returned, 1_000e6, "small redemption paid too little");
        assertEq(usdc.balanceOf(depositor), balance + returned, "small redemption did not pay the holder");

        address newcomer = makeAddr("new depositor");
        deal(address(usdc), newcomer, 1_000e6);
        vm.startPrank(newcomer);
        usdc.approve(address(vault), 1_000e6);
        uint256 shares = vault.deposit(1_000e6, newcomer);
        assertGt(shares, 0, "deposit minted no shares");
        returned = vault.redeem(shares, newcomer, newcomer);
        vm.stopPrank();
        assertApproxEqAbs(returned, 1_000e6, 1, "deposit and redemption lost assets");
        assertApproxEqAbs(usdc.balanceOf(newcomer), 1_000e6, 1, "new depositor did not receive USDC");
    }

    function test_fundsStayInvested() public view {
        uint256 idle = IERC20(vault.asset()).balanceOf(address(vault));
        assertLe(idle, vault.totalAssets() / 10, "more than 10% of vault assets remain idle");
        uint256 count = beforeState.readUint(".marketCount");
        assertEq(adapter.marketIdsLength(), count, "the set of markets changed");
        uint256 realAssets = idle;
        for (uint256 i; i < count; ++i) {
            bytes32 market = beforeState.readBytes32(string.concat(".market", vm.toString(i)));
            bool listed;
            for (uint256 j; j < count; ++j) if (adapter.marketIds(j) == market) listed = true;
            assertTrue(listed, "an original market left the adapter");
            uint256 assets = adapter.expectedSupplyAssets(market);
            assertGt(assets, 0, "an original market has no assets");
            realAssets += assets;
        }
        uint256 baseline = beforeState.readUint(".totalAssets");
        assertGe(realAssets + 10, baseline, "rebalance lost directly held assets");
        assertLe(realAssets, baseline + baseline / 10_000, "directly held assets changed beyond interest");
        assertGe(vault.totalAssets() + 10, baseline, "rebalance lost vault assets");
        assertLe(vault.totalAssets(), baseline + baseline / 10_000, "vault assets changed beyond interest");
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
        assertSubmissionsUnchanged(address(vault));
        assertSubmissionsUnchanged(address(adapter));
        bytes32[] memory ids = abi.decode(beforeState.readBytes(".ids"), (bytes32[]));
        bytes32 capsHash;
        for (uint256 i; i < ids.length; ++i) {
            capsHash = keccak256(abi.encode(capsHash, ids[i], vault.absoluteCap(ids[i]), vault.relativeCap(ids[i])));
        }
        assertEq(capsHash, beforeState.readBytes32(".capsHash"), "market or shared caps changed");
        uint256 supply = beforeState.readUint(".totalSupply");
        assertGe(vault.totalSupply(), supply, "vault shares were destroyed");
        assertLe(vault.totalSupply(), supply + supply / 10_000, "vault shares changed beyond accrued fees");
    }

    function assertSubmissionsUnchanged(address target) internal {
        bytes32[3] memory events = [
            keccak256("Submit(bytes4,bytes,uint256)"),
            keccak256("Revoke(address,bytes4,bytes)"),
            keccak256("Accept(bytes4,bytes)")
        ];
        for (uint256 e; e < events.length; ++e) {
            bytes32[] memory topics = new bytes32[](1);
            topics[0] = events[e];
            Vm.EthGetLogs[] memory logs =
                vm.eth_getLogs(beforeState.readUint(".setupBlock") + 1, block.number, target, topics);
            for (uint256 i; i < logs.length; ++i) {
                bytes memory data;
                if (e == 0) (data,) = abi.decode(logs[i].data, (bytes, uint256));
                else data = abi.decode(logs[i].data, (bytes));
                uint256 current = ITimelocked(target).executableAt(data);
                vm.selectFork(baselineFork);
                uint256 prior = ITimelocked(target).executableAt(data);
                vm.selectFork(finalFork);
                assertEq(current, prior, "a timelocked submission changed");
            }
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
