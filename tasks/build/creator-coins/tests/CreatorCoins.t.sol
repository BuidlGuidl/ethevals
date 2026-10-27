// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {CreatorCoins} from "../workspace/src/CreatorCoins.sol";
import {MainnetSetup, TestToken, TestFactory, TestPool} from "./MainnetSetup.sol";

interface TestPlatform {
    function create(string calldata, string calldata) external returns (address);
    function collect(address) external;
    function setPayoutRecipient(address, address) external;
}

contract CreatorCoinsTest is MainnetSetup {
    TestPlatform internal platform;
    address internal creator;
    address internal otherCreator;
    address internal treasury;
    address internal stranger;
    address internal recipient;
    address internal trader;
    address private callbackPool;

    function setUp() public {
        installMainnet();
        creator = makeAddr("creator");
        otherCreator = makeAddr("other creator");
        treasury = makeAddr("platform fees");
        stranger = makeAddr("stranger");
        recipient = makeAddr("new recipient");
        trader = makeAddr("trader");
        vm.deal(trader, 100 ether);
        vm.startPrank(trader);
        TestToken(WETH).deposit{value: 50 ether}();
        TestToken(WETH).approve(address(this), type(uint256).max);
        vm.stopPrank();
        platform = TestPlatform(address(new CreatorCoins(treasury)));
    }

    function launch(address who, string memory name) internal returns (address coin) {
        vm.prank(who);
        coin = platform.create(name, "COIN");
    }

    function poolFor(address coin) internal view returns (TestPool) {
        return TestPool(TestFactory(FACTORY).getPool(coin, WETH, 10000));
    }

    function swap(address coin, bool sell, uint256 amount) internal returns (uint256 output, uint256 fee) {
        TestPool pool = poolFor(coin);
        address input = sell ? coin : WETH;
        vm.prank(trader);
        TestToken(input).approve(address(this), type(uint256).max);
        bool zeroForOne = pool.token0() == input;
        callbackPool = address(pool);
        (int256 d0, int256 d1) = pool.swap(
            trader, zeroForOne, int256(amount), zeroForOne ? MIN_PRICE : MAX_PRICE, abi.encode(trader)
        );
        callbackPool = address(0);
        uint256 paid = uint256(zeroForOne ? d0 : d1);
        assertEq(paid, amount, "trade must consume the requested input");
        output = uint256(-(zeroForOne ? d1 : d0));
        // Every paid input step charges 1%; integer rounding costs at most a few wei.
        fee = amount / 100;
    }

    function uniswapV3SwapCallback(int256 d0, int256 d1, bytes calldata data) external {
        require(msg.sender == callbackPool, "unexpected swap callback");
        address payer = abi.decode(data, (address));
        TestPool pool = TestPool(msg.sender);
        if (d0 > 0) TestToken(pool.token0()).transferFrom(payer, msg.sender, uint256(d0));
        if (d1 > 0) TestToken(pool.token1()).transferFrom(payer, msg.sender, uint256(d1));
    }

    function money(address who) internal view returns (uint256) {
        return who.balance + TestToken(WETH).balanceOf(who);
    }

    function assertOpening(address coin) internal {
        TestPool pool = poolFor(coin);
        assertEq(TestToken(coin).totalSupply(), 1_000_000_000 * 10 ** TestToken(coin).decimals(), "fixed 1B supply");
        assertApproxEqAbs(TestToken(coin).balanceOf(address(pool)), TestToken(coin).totalSupply(), 100_000, "whole supply in pool");
        assertEq(pool.fee(), 10000, "1% fee tier");
        (uint256 bought,) = swap(coin, false, 0.000001 ether);
        // Gross price includes the 1% swap fee and up to one 200-tick spacing either way.
        uint256 price = 0.000001 ether * 10 ** TestToken(coin).decimals() / bought;
        uint256 grossPrice = uint256(10_000_000_000) * 100 / 99;
        // 1.0001 ** 200 = 1.020200319893934..., rounded outwards.
        assertGe(price, grossPrice * 1e12 / 1_020_200_319_894, "opening price below 10 ETH market cap");
        assertLe(price, grossPrice * 1_020_200_319_894 / 1e12 + 1, "opening price above 10 ETH market cap");
    }

    function roundTrip(address coin) internal returns (uint256 coinFees, uint256 wethFees) {
        (uint256 bought, uint256 buyFee) = swap(coin, false, 1 ether);
        (, coinFees) = swap(coin, true, bought / 2);
        wethFees = buyFee;
    }

    function quoteCoin(address coin, uint256 amount) internal returns (uint256 value) {
        if (amount == 0) return 0;
        uint256 snapshot = vm.snapshotState();
        (value,) = swap(coin, true, amount);
        assertTrue(vm.revertToState(snapshot), "restore quote snapshot");
    }

    function assertSplit(address coin, address payee, uint256 coinFees, uint256 wethFees) internal {
        uint256 beforeCoin = TestToken(coin).balanceOf(payee);
        uint256 beforePlatformCoin = TestToken(coin).balanceOf(treasury);
        uint256 beforeMoney = money(payee);
        uint256 beforePlatformMoney = money(treasury);
        uint256 conversionValue = quoteCoin(coin, coinFees);
        platform.collect(coin);
        uint256 creatorCoin = TestToken(coin).balanceOf(payee) - beforeCoin;
        uint256 platformCoin = TestToken(coin).balanceOf(treasury) - beforePlatformCoin;
        uint256 paidCoin = creatorCoin + platformCoin;
        uint256 creatorMoney = money(payee) - beforeMoney;
        uint256 platformMoney = money(treasury) - beforePlatformMoney;
        if (paidCoin != 0) {
            assertApproxEqAbs(paidCoin, coinFees, 100_000, "all coin-side fees paid");
            assertApproxEqAbs(creatorCoin, coinFees * 70 / 100, 100_000, "creator gets 70% of coin fees");
            assertApproxEqAbs(platformCoin, coinFees * 30 / 100, 100_000, "platform gets 30% of coin fees");
            assertApproxEqAbs(creatorMoney, wethFees * 70 / 100, 10, "creator gets 70% of WETH fees");
            assertApproxEqAbs(platformMoney, wethFees * 30 / 100, 10, "platform gets 30% of WETH fees");
        } else {
            // Conversion can trade before or after collection. Allow its fee and price impact.
            uint256 expected = wethFees + conversionValue;
            uint256 tolerance = conversionValue * 2 / 100 + 10;
            assertApproxEqAbs(creatorMoney, expected * 70 / 100, tolerance, "creator gets converted fees");
            assertApproxEqAbs(platformMoney, expected * 30 / 100, tolerance, "platform gets converted fees");
        }
    }

    function test_everyCoinOpensAtTenEth() public {
        for (uint256 i; i < 8; ++i) {
            address coin = launch(makeAddr(string.concat("creator ", vm.toString(i))), vm.toString(i));
            emit log_named_address(coin < WETH ? "coin is token0" : "coin is token1", coin);
            assertOpening(coin);
        }
    }

    function test_strangerCreatedPoolFirst() public {
        for (uint256 i; i < 2; ++i) {
            uint256 snapshot = vm.snapshotState();
            address predicted = launch(creator, "same block launch");
            assertTrue(vm.revertToState(snapshot), "restore address prediction");
            vm.startPrank(stranger);
            TestPool pool = TestPool(TestFactory(FACTORY).createPool(predicted, WETH, 10000));
            uint160 open = predicted < WETH ? uint160(uint256(2 ** 96) / 10000) : uint160(2 ** 96 * 10000);
            pool.initialize(i == 0 ? open * 10 : open / 10);
            vm.stopPrank();
            address coin = launch(creator, "same block launch");
            // A design can choose a different address after discovering an occupied pool.
            assertOpening(coin);
        }
    }

    function test_feesAreThisCoins() public {
        address x = launch(creator, "traded coin");
        address y = launch(otherCreator, "idle coin");
        (uint256 coinFees, uint256 wethFees) = roundTrip(x);
        // Unrelated balances cannot become the idle coin's trading fees.
        vm.prank(trader);
        TestToken(WETH).transfer(address(platform), 0.123 ether);
        try platform.collect(y) {} catch {}
        assertEq(money(otherCreator), 0, "idle creator gets no fees");
        assertEq(money(treasury), 0, "idle pool pays no platform fees");
        assertEq(TestToken(x).balanceOf(otherCreator), 0, "idle creator gets no other coin");
        assertSplit(x, creator, coinFees, wethFees);
        assertEq(money(otherCreator), 0, "traded coin cannot pay the idle creator");
    }

    function test_coinSideFeesPaidOut() public {
        address coin = launch(creator, "sell fees");
        (uint256 coinFees, uint256 wethFees) = roundTrip(coin);
        assertSplit(coin, creator, coinFees, wethFees);
        assertLe(TestToken(coin).balanceOf(address(platform)), 100_000, "contract retains only coin dust");
    }

    function test_liquidityStaysPut() public {
        address coin = launch(creator, "permanent position");
        swap(coin, false, 0.1 ether);
        TestPool pool = poolFor(coin);
        assertGt(pool.liquidity(), 0, "buy enters the coin position");
        uint256 snapshot = vm.snapshotState();
        uint160[3] memory prices;
        uint128[3] memory liquidities;
        for (uint256 i; i < 3; ++i) {
            roundTrip(coin);
            (prices[i],,,,,,) = pool.slot0();
            liquidities[i] = pool.liquidity();
        }
        assertTrue(vm.revertToState(snapshot), "restore liquidity control");
        for (uint256 i; i < 3; ++i) {
            roundTrip(coin);
            vm.prank(i == 0 ? stranger : i == 1 ? creator : treasury);
            platform.collect(coin);
            assertLiquidityAtPrice(pool, prices[i], liquidities[i]);
            vm.prank(creator);
            platform.setPayoutRecipient(coin, i == 1 ? creator : recipient);
            assertLiquidityAtPrice(pool, prices[i], liquidities[i]);
        }
    }

    function assertLiquidityAtPrice(TestPool pool, uint160 price, uint128 liquidity) internal {
        (uint160 current,,,,,,) = pool.slot0();
        if (current != price) {
            // Fee conversion can move price. Trade back without changing any position.
            vm.startPrank(trader);
            TestToken(pool.token0()).approve(address(this), type(uint256).max);
            TestToken(pool.token1()).approve(address(this), type(uint256).max);
            vm.stopPrank();
            callbackPool = address(pool);
            pool.swap(trader, current > price, type(int256).max, price, abi.encode(trader));
            callbackPool = address(0);
        }
        (uint160 actual,,,,,,) = pool.slot0();
        assertEq(actual, price, "compare liquidity at the control price");
        assertEq(pool.liquidity(), liquidity, "required calls keep the control principal");
    }

    function test_onlyCreatorRedirects() public {
        address coin = launch(creator, "creator rights");
        vm.prank(stranger);
        try platform.setPayoutRecipient(coin, stranger) {} catch {}
        (uint256 coinFees, uint256 wethFees) = roundTrip(coin);
        assertSplit(coin, creator, coinFees, wethFees);
        assertEq(money(stranger), 0, "stranger cannot redirect WETH");
        assertEq(TestToken(coin).balanceOf(stranger), 0, "stranger cannot redirect coin");
        vm.prank(creator);
        platform.setPayoutRecipient(coin, recipient);
        uint256 oldCoin = TestToken(coin).balanceOf(creator);
        uint256 oldMoney = money(creator);
        (coinFees, wethFees) = roundTrip(coin);
        assertSplit(coin, recipient, coinFees, wethFees);
        assertEq(TestToken(coin).balanceOf(creator), oldCoin, "old recipient gets no later coin fees");
        assertEq(money(creator), oldMoney, "old recipient gets no later WETH fees");
    }

    function test_strangerCollectGetsNothing() public {
        address coin = launch(creator, "permissionless collection");
        (uint256 coinFees, uint256 wethFees) = roundTrip(coin);
        // assertSplit collects as this test contract, a caller with no payout rights.
        uint256 beforeMoney = money(address(this));
        assertSplit(coin, creator, coinFees, wethFees);
        assertEq(money(address(this)), beforeMoney, "collector gets no WETH or ETH");
        assertEq(TestToken(coin).balanceOf(address(this)), 0, "collector gets no coin");
    }
}
