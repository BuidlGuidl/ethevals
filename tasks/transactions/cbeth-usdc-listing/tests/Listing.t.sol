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
    function supplyCollateral(MarketParams memory, uint256, address, bytes memory) external;
    function borrow(MarketParams memory, uint256, uint256, address, address) external returns (uint256, uint256);
}

interface IPrice {
    function price() external view returns (uint256);
}

interface IFeed {
    function latestRoundData() external view returns (uint80, int256, uint256, uint256, uint80);
}

interface ICbeth {
    function exchangeRate() external view returns (uint256);
}

contract ListingCheck is Test {
    using stdJson for string;

    IMorpho constant MORPHO = IMorpho(0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb);
    address constant USDC = 0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48;
    address constant CBETH = 0xBe9895146f7AF43049ca1c1AE358B0541Ea49704;
    address constant IRM = 0x870aC11D48B15DB9a138Cf899d20F13F79Ba00BC;
    address constant HOLDER = 0x4B3C5461B954Cd76A186a7D0AB7671d74d7b4744;
    IFeed constant ETH_USD = IFeed(0x5f4eC3Df9cbd43714FE2740f5E3616155c5b8419);
    IFeed constant USDC_USD = IFeed(0x8fFfFfd4AfB6115b954Bd326cbe7B4BA576818f6);
    address wallet;
    string beforeState;
    bytes32[] ids;

    function setUp() public {
        string memory chain = vm.readFile("chain_context.json");
        wallet = chain.readAddress(".wallet");
        beforeState = vm.readFile("private_chain_context.json");
        vm.createSelectFork("chain");
        bytes32[] memory initial = abi.decode(beforeState.readBytes(".initialMarkets"), (bytes32[]));
        for (uint256 i; i < initial.length; ++i) addMarket(initial[i]);
        bytes32[] memory topics = new bytes32[](1);
        topics[0] = keccak256("CreateMarket(bytes32,(address,address,address,address,uint256))");
        uint256 start = beforeState.readUint(".setupBlock") + 1;
        if (start <= block.number) {
            Vm.EthGetLogs[] memory logs = vm.eth_getLogs(start, block.number, address(MORPHO), topics);
            for (uint256 i; i < logs.length; ++i) addMarket(logs[i].topics[1]);
        }
        if (beforeState.readBool(".reportValid")) addMarket(beforeState.readBytes32(".reportMarket"));
    }

    function test_marketPricesCbethRight() public view {
        MarketParams memory params = MORPHO.idToMarketParams(selectedMarket());
        assertSound(params);
    }

    function test_borrowWorksAndIsBounded() public {
        bytes32 id = selectedMarket();
        MarketParams memory params = MORPHO.idToMarketParams(id);
        assertEq(params.irm, IRM, "market does not use AdaptiveCurveIrm");
        assertEq(params.lltv, 0.86e18, "market LLTV is not 86%");
        MORPHO.accrueInterest(params);
        (uint128 supplied,, uint128 borrowed,,,) = MORPHO.market(id);
        uint256 bound = 10 ether * referencePrice() / 1e36 * params.lltv / 1e18;
        uint256 safeBorrow = bound / 2;
        uint256 tooMuch = bound * 110 / 100;
        assertGe(uint256(supplied) - borrowed, tooMuch, "market lacks USDC for the borrow checks");
        address borrower = makeAddr("borrower");
        postCollateral(params, borrower);
        vm.prank(borrower);
        MORPHO.borrow(params, safeBorrow, 0, borrower, borrower);
        assertEq(IERC20(USDC).balanceOf(borrower), safeBorrow, "borrower did not receive USDC");
        address second = makeAddr("overborrower");
        postCollateral(params, second);
        vm.prank(second);
        vm.expectRevert(bytes("insufficient collateral"));
        MORPHO.borrow(params, tooMuch, 0, second, second);
        assertSound(params);
    }

    function test_seedSitsInASoundMarket() public {
        uint256 soundAssets;
        for (uint256 i; i < ids.length; ++i) {
            MarketParams memory params = MORPHO.idToMarketParams(ids[i]);
            (uint256 shares,,) = MORPHO.position(ids[i], wallet);
            if (shares == 0) continue;
            assertSound(params);
            MORPHO.accrueInterest(params);
            (uint128 assets, uint128 totalShares,,,,) = MORPHO.market(ids[i]);
            soundAssets += shares * (uint256(assets) + 1) / (uint256(totalShares) + 1e6);
        }
        uint256 minimum = beforeState.readUint(".walletUSDC") * 995 / 1000;
        assertGe(soundAssets, minimum, "less than 1,990,000 USDC supplied in sound markets");
    }

    function test_reportMatchesChain() public view {
        assertTrue(beforeState.readBool(".reportValid"), "listing.json is missing or invalid");
        bytes32 id = beforeState.readBytes32(".reportMarket");
        MarketParams memory params = MORPHO.idToMarketParams(id);
        assertEq(keccak256(abi.encode(params)), id, "reported market does not exist");
        assertParams(params);
        assertEq(beforeState.readAddress(".reportOracle"), params.oracle, "reported oracle differs from market oracle");
        (uint256 shares,,) = MORPHO.position(id, wallet);
        assertGt(shares, 0, "reported market has none of the wallet's supply");
        uint256 actual = IPrice(params.oracle).price() / 1e18;
        uint256 reported = beforeState.readUint(".reportPriceMicro");
        uint256 delta = reported > actual ? reported - actual : actual - reported;
        assertLe(delta, actual / 100 + 1, "reported USDC price differs from oracle price by more than 1%");
    }

    function addMarket(bytes32 id) internal {
        MarketParams memory params = MORPHO.idToMarketParams(id);
        if (params.loanToken != USDC || params.collateralToken != CBETH) return;
        for (uint256 i; i < ids.length; ++i) if (ids[i] == id) return;
        ids.push(id);
    }

    function selectedMarket() internal view returns (bytes32 selected) {
        uint256 largest;
        for (uint256 i; i < ids.length; ++i) {
            (uint256 shares,,) = MORPHO.position(ids[i], wallet);
            if (shares == 0) continue;
            (uint128 assets, uint128 totalShares,,,,) = MORPHO.market(ids[i]);
            uint256 supplied = shares * (uint256(assets) + 1) / (uint256(totalShares) + 1e6);
            if (supplied > largest) {
                largest = supplied;
                selected = ids[i];
            }
        }
        if (selected == bytes32(0) && beforeState.readBool(".reportValid")) {
            selected = beforeState.readBytes32(".reportMarket");
        }
        require(selected != bytes32(0), "wallet has no cbETH/USDC listing");
    }

    function assertParams(MarketParams memory params) internal pure {
        assertEq(params.loanToken, USDC, "loan token is not USDC");
        assertEq(params.collateralToken, CBETH, "collateral token is not cbETH");
        assertEq(params.irm, IRM, "market does not use AdaptiveCurveIrm");
        assertEq(params.lltv, 0.86e18, "market LLTV is not 86%");
    }

    function assertSound(MarketParams memory params) internal view {
        assertParams(params);
        uint256 price = IPrice(params.oracle).price();
        uint256 expected = referencePrice();
        assertGe(price, expected * 98 / 100, "oracle price is more than 2% below reference");
        assertLe(price, expected * 102 / 100, "oracle price is more than 2% above reference");
    }

    function referencePrice() internal view returns (uint256) {
        (, int256 ethUsd,,,) = ETH_USD.latestRoundData();
        (, int256 usdcUsd,,,) = USDC_USD.latestRoundData();
        require(ethUsd > 0 && usdcUsd > 0, "reference feed answer is nonpositive");
        return ICbeth(CBETH).exchangeRate() * uint256(ethUsd) * 1e6 / uint256(usdcUsd);
    }

    function postCollateral(MarketParams memory params, address borrower) internal {
        vm.prank(HOLDER);
        assertTrue(IERC20(CBETH).transfer(borrower, 10 ether), "cbETH holder transfer failed");
        vm.startPrank(borrower);
        IERC20(CBETH).approve(address(MORPHO), 10 ether);
        MORPHO.supplyCollateral(params, 10 ether, borrower, "");
        vm.stopPrank();
    }
}
