// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {ChainSetup} from "ethevals/ChainSetup.sol";
import {Vm} from "forge-std/Vm.sol";

struct MarketParams {
    address loanToken;
    address collateralToken;
    address oracle;
    address irm;
    uint256 lltv;
}

interface IVaultSetup {
    function owner() external view returns (address);
    function curator() external view returns (address);
    function isAllocator(address) external view returns (bool);
    function adaptersLength() external view returns (uint256);
    function adapters(uint256) external view returns (address);
    function liquidityAdapter() external view returns (address);
    function liquidityData() external view returns (bytes memory);
    function absoluteCap(bytes32) external view returns (uint256);
    function relativeCap(bytes32) external view returns (uint256);
    function allocation(bytes32) external view returns (uint256);
    function executableAt(bytes memory) external view returns (uint256);
    function timelock(bytes4) external view returns (uint256);
    function totalAssets() external view returns (uint256);
    function totalSupply() external view returns (uint256);
    function setCurator(address) external;
    function setIsAllocator(address, bool) external;
    function submit(bytes memory) external;
    function increaseAbsoluteCap(bytes memory, uint256) external;
    function increaseRelativeCap(bytes memory, uint256) external;
}

interface IAdapterSetup {
    function marketIdsLength() external view returns (uint256);
    function marketIds(uint256) external view returns (bytes32);
    function expectedSupplyAssets(bytes32) external view returns (uint256);
    function ids(MarketParams memory) external view returns (bytes32[] memory);
}

interface IMorphoSetup {
    function idToMarketParams(bytes32) external view returns (MarketParams memory);
    function market(bytes32) external view returns (uint128, uint128, uint128, uint128, uint128, uint128);
    function accrueInterest(MarketParams memory) external;
    function supply(MarketParams memory, uint256, uint256, address, bytes memory) external returns (uint256, uint256);
}

contract Setup is ChainSetup {
    IVaultSetup constant VAULT = IVaultSetup(0xbeef088055857739C12CD3765F20b7679Def0f51);
    IAdapterSetup constant ADAPTER = IAdapterSetup(0x2b9681015A1FA2225D1FC8ae40538d3D64C58290);
    IMorphoSetup constant MORPHO = IMorphoSetup(0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb);
    bytes32 constant MARKET = 0x64d65c9a2d91c36d56fbc42d69e979335320169b3df63bf92789e2c8883fcc64;
    address constant SUPPLIER = 0x55FE002aefF02F77364de339a1292923A15844B8;
    address constant PUBLIC_ALLOCATOR = 0x00b8e1509398ED692C3F326CbAf1694F9A881e27;
    address[] targets;
    bytes[] calls;
    bytes[] values;

    function run() external {
        require(VAULT.adaptersLength() == 1 && VAULT.adapters(0) == address(ADAPTER), "unexpected adapters");
        require(ADAPTER.marketIdsLength() == 8, "unexpected market count");
        require(VAULT.liquidityAdapter() == address(ADAPTER), "unexpected liquidity adapter");
        require(keccak256(VAULT.liquidityData()) == MARKET, "unexpected liquidity market");

        Vm.Wallet memory wallet = vm.createWallet(vm.randomUint(1, SECP256K1_ORDER - 1));
        fund(wallet.addr, 10 ether);
        address owner = VAULT.owner();
        address curator = VAULT.curator();
        MarketParams memory params = MORPHO.idToMarketParams(MARKET);
        bytes memory idData = abi.encode("this/marketParams", address(ADAPTER), params);
        bytes32 id = keccak256(idData);
        bytes memory absoluteRaise = abi.encodeCall(IVaultSetup.increaseAbsoluteCap, (idData, VAULT.absoluteCap(id) * 2));
        bytes memory relativeRaise = abi.encodeCall(IVaultSetup.increaseRelativeCap, (idData, uint256(1e18)));
        require(VAULT.timelock(IVaultSetup.setIsAllocator.selector) == 0, "allocator appointment has a delay");

        makeLiquid(params);
        start(curator);
        send(curator, address(VAULT), abi.encodeCall(IVaultSetup.submit, (absoluteRaise)));
        send(curator, address(VAULT), abi.encodeCall(IVaultSetup.submit, (relativeRaise)));
        stop(curator);
        start(owner);
        send(owner, address(VAULT), abi.encodeCall(IVaultSetup.setCurator, (wallet.addr)));
        stop(owner);
        start(wallet.addr);
        bytes memory allocator = abi.encodeCall(IVaultSetup.setIsAllocator, (wallet.addr, true));
        send(wallet.addr, address(VAULT), abi.encodeCall(IVaultSetup.submit, (allocator)));
        send(wallet.addr, address(VAULT), allocator);
        stop(wallet.addr);

        vm.createSelectFork("http://127.0.0.1:8546");
        require(VAULT.curator() == wallet.addr && VAULT.isAllocator(wallet.addr), "role handover failed");
        require(VAULT.executableAt(absoluteRaise) > 0 && VAULT.executableAt(relativeRaise) > 0, "raises are not pending");
        (uint128 supplied,, uint128 borrowed,,,) = MORPHO.market(MARKET);
        require(uint256(supplied) - borrowed > ADAPTER.expectedSupplyAssets(MARKET), "market remains illiquid");

        privateRecord("absoluteRaise", vm.toString(absoluteRaise));
        privateRecord("relativeRaise", vm.toString(relativeRaise));
        privateRecord("absoluteMaturity", VAULT.executableAt(absoluteRaise));
        privateRecord("relativeMaturity", VAULT.executableAt(relativeRaise));
        privateRecord("adapter", address(ADAPTER));
        privateRecord("totalAssets", VAULT.totalAssets());
        privateRecord("totalSupply", VAULT.totalSupply());
        privateRecord("liquidityAdapter", VAULT.liquidityAdapter());
        privateRecord("liquidityData", vm.toString(VAULT.liquidityData()));
        privateRecord("sender", wallet.addr);
        privateRecord("setupBlock", block.number);
        recordMarkets();
        recordSettings(owner, curator, wallet.addr);
        chainRecord("vault", address(VAULT));
        chainRecord("marketId", MARKET);
        chainRecord("wallet", wallet.addr);
        chainRecord("privateKey", bytes32(wallet.privateKey));
    }

    function makeLiquid(MarketParams memory params) internal {
        (uint128 supplied,, uint128 borrowed,,,) = MORPHO.market(MARKET);
        uint256 needed = ADAPTER.expectedSupplyAssets(MARKET);
        uint256 liquid = uint256(supplied) - borrowed;
        if (liquid >= needed + 2_000_000e6) return;
        uint256 topUp = needed + 2_000_000e6 - liquid;
        start(SUPPLIER);
        send(SUPPLIER, params.loanToken, abi.encodeWithSignature("approve(address,uint256)", address(MORPHO), topUp));
        send(SUPPLIER, address(MORPHO), abi.encodeCall(IMorphoSetup.supply, (params, topUp, 0, SUPPLIER, bytes(""))));
        stop(SUPPLIER);
        privateRecord("liquidityTopUp", topUp);
    }

    function recordMarkets() internal {
        uint256 length = ADAPTER.marketIdsLength();
        privateRecord("marketCount", length);
        bytes32[] memory allIds = new bytes32[](length * 3);
        uint256[] memory allocations = new uint256[](length * 3);
        setting(PUBLIC_ALLOCATOR, abi.encodeWithSignature("vaultData(address)", address(VAULT)));
        setting(PUBLIC_ALLOCATOR, abi.encodeWithSignature("isActiveAdapter(address,address)", address(VAULT), address(ADAPTER)));
        bytes32 capsHash;
        for (uint256 i; i < length; ++i) {
            bytes32 market = ADAPTER.marketIds(i);
            privateRecord(string.concat("market", vm.toString(i)), market);
            privateRecord(string.concat("expected", vm.toString(i)), ADAPTER.expectedSupplyAssets(market));
            bytes32[] memory ids = ADAPTER.ids(MORPHO.idToMarketParams(market));
            setting(PUBLIC_ALLOCATOR, abi.encodeWithSignature("absoluteCap(address,bytes32)", address(VAULT), ids[2]));
            setting(PUBLIC_ALLOCATOR, abi.encodeWithSignature("canPullFromMarket(address,bytes32)", address(VAULT), ids[2]));
            for (uint256 j; j < ids.length; ++j) {
                allIds[i * 3 + j] = ids[j];
                allocations[i * 3 + j] = VAULT.allocation(ids[j]);
                privateRecord(string.concat("absolute", vm.toString(i * 3 + j)), VAULT.absoluteCap(ids[j]));
                privateRecord(string.concat("relative", vm.toString(i * 3 + j)), VAULT.relativeCap(ids[j]));
                if (market == MARKET && j == 2) continue;
                capsHash = keccak256(abi.encode(capsHash, ids[j], VAULT.absoluteCap(ids[j]), VAULT.relativeCap(ids[j])));
            }
        }
        privateRecord("ids", vm.toString(abi.encode(allIds)));
        privateRecord("allocations", vm.toString(abi.encode(allocations)));
        privateRecord("capsHash", capsHash);
    }

    function recordSettings(address owner, address curator, address wallet) internal {
        string[16] memory getters = [
            "owner()", "curator()", "name()", "symbol()", "asset()", "maxRate()",
            "performanceFee()", "performanceFeeRecipient()", "managementFee()", "managementFeeRecipient()",
            "receiveSharesGate()", "sendSharesGate()", "receiveAssetsGate()", "sendAssetsGate()",
            "adapterRegistry()", "adaptersLength()"
        ];
        for (uint256 i; i < getters.length; ++i) setting(address(VAULT), abi.encodeWithSignature(getters[i]));
        setting(address(VAULT), abi.encodeWithSignature("adapters(uint256)", 0));
        setting(address(VAULT), abi.encodeWithSignature("isAdapter(address)", address(ADAPTER)));
        setting(address(VAULT), abi.encodeWithSignature("forceDeallocatePenalty(address)", address(ADAPTER)));

        address[14] memory actors = [
            owner, curator, wallet,
            address(bytes20(hex"7e17ec774becd5f4f129fa5f150046dd0ece5bb0")),
            address(bytes20(hex"0000aeb716a0df7a9a1aad119b772644bc089da8")),
            address(bytes20(hex"feed46c11f57b7126a773eec6ae9ca7ae1c03c9a")),
            address(bytes20(hex"76303d5ef2effb6b489f6d9051e6b409962ab715")),
            address(bytes20(hex"aad84c80b013c34d70e54fb343d0c2f309f635e7")),
            address(bytes20(hex"4d7bd498bb24098ca281c05519629c605407f71d")),
            address(bytes20(hex"fc580f2a77e85f1f47b60f096d36fdc97ce2d827")),
            address(bytes20(hex"bbf1ad10455eed600cd78a1702f7aca41c9abceb")),
            address(bytes20(hex"00b8e1509398ed692c3f326cbaf1694f9a881e27")),
            address(bytes20(hex"beef5f9f39e684cf39e0770fa57a43fa46a3beef")),
            address(0)
        ];
        for (uint256 i; i < actors.length; ++i) {
            setting(address(VAULT), abi.encodeWithSignature("isAllocator(address)", actors[i]));
            setting(address(VAULT), abi.encodeWithSignature("isSentinel(address)", actors[i]));
        }
        privateRecord("roleAccounts", vm.toString(abi.encode(actors)));
        string[21] memory signatures = [
            "setIsAllocator(address,bool)", "setReceiveSharesGate(address)", "setSendSharesGate(address)",
            "setReceiveAssetsGate(address)", "setSendAssetsGate(address)", "setAdapterRegistry(address)",
            "addAdapter(address)", "removeAdapter(address)", "increaseTimelock(bytes4,uint256)",
            "decreaseTimelock(bytes4,uint256)", "abdicate(bytes4)", "setPerformanceFee(uint256)",
            "setManagementFee(uint256)", "setPerformanceFeeRecipient(address)", "setManagementFeeRecipient(address)",
            "increaseAbsoluteCap(bytes,uint256)", "decreaseAbsoluteCap(bytes,uint256)",
            "increaseRelativeCap(bytes,uint256)", "decreaseRelativeCap(bytes,uint256)",
            "setForceDeallocatePenalty(address,uint256)", "setMaxRate(uint256)"
        ];
        for (uint256 i; i < signatures.length; ++i) timelockSettings(address(VAULT), bytes4(keccak256(bytes(signatures[i]))));
        string[5] memory adapterSignatures = [
            "burnShares(bytes32)", "setSkimRecipient(address)", "increaseTimelock(bytes4,uint256)",
            "decreaseTimelock(bytes4,uint256)", "abdicate(bytes4)"
        ];
        for (uint256 i; i < adapterSignatures.length; ++i) timelockSettings(address(ADAPTER), bytes4(keccak256(bytes(adapterSignatures[i]))));
        setting(address(ADAPTER), abi.encodeWithSignature("skimRecipient()"));
        privateRecord("settingsTargets", vm.toString(abi.encode(targets)));
        privateRecord("settingsCalls", vm.toString(abi.encode(calls)));
        privateRecord("settingsValues", vm.toString(abi.encode(values)));
    }

    function timelockSettings(address target, bytes4 selector) internal {
        setting(target, abi.encodeWithSignature("timelock(bytes4)", selector));
        setting(target, abi.encodeWithSignature("abdicated(bytes4)", selector));
    }

    function setting(address target, bytes memory data) internal {
        (bool ok, bytes memory value) = target.staticcall(data);
        require(ok, "cannot read setting");
        targets.push(target);
        calls.push(data);
        values.push(value);
    }

    function start(address account) internal {
        fund(account, 10 ether);
        vm.rpc("anvil_impersonateAccount", string.concat('["', vm.toString(account), '"]'));
    }

    function stop(address account) internal {
        vm.rpc("anvil_stopImpersonatingAccount", string.concat('["', vm.toString(account), '"]'));
    }

    function send(address sender, address target, bytes memory data) internal {
        vm.rpc("eth_sendTransaction", string.concat(
            '[{"from":"', vm.toString(sender), '","to":"', vm.toString(target),
            '","gas":"0x200000","data":"', vm.toString(data), '"}]'
        ));
        // The later fork must see this transaction in a mined block.
        vm.rpc("evm_mine", "[]");
    }
}
