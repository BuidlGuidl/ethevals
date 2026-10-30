// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {Test} from "forge-std/Test.sol";
import {IPriceFeed} from "../workspace/src/interfaces/IPriceFeed.sol";
import {DeployPriceFeeds} from "../workspace/script/DeployPriceFeeds.s.sol";
import {MockFeed, MockWstETH, MockStETH, MockRETH} from "./Mocks.sol";

contract Forwarder {
    function forward(address target, bytes calldata data) external returns (bytes memory) {
        (bool ok, bytes memory ret) = target.call(data);
        if (!ok) {
            assembly {
                revert(add(ret, 0x20), mload(ret))
            }
        }
        return ret;
    }
}

contract CdpPriceFeedTest is Test {
    // Chainlink proxies on mainnet, from the feed directory.
    address constant ETH_USD = 0x5f4eC3Df9cbd43714FE2740f5E3616155c5b8419;
    address constant ETH_USD_SVR = 0x5147eA642CAEF7BD9c1265AadcA78f997AbB9649;
    address constant ETH_USD_SHARED_SVR = 0xd82562bb17557231Cd871e1B2525F3AB8d63D409;
    address constant STETH_USD = 0xCfE54B5cD566aB89272946F602D76Ea879CAb4a8;
    address constant STETH_ETH = 0x86392dC19c0b719886221c78AB11eb8Cf5c52812;
    address constant WSTETH_USD = 0x164b276057258d81941e97B0a900D4C7B358bCe0;
    address constant RETH_ETH = 0x536218f9E9Eb48863970252233c8F271f554C2d0;
    // The tokens whose staking rates a feed reads.
    address constant WSTETH = 0x7f39C581F595B53c5cb19bD0b3f8dA6c935E2Ca0;
    address constant STETH = 0xae7ab96520DE3A18E5e111B5EaAb095312D7fE84;
    address constant RETH = 0xae78736Cd615f374D3085123A210448E74Fc6393;

    uint256 constant BLOCK = 12;
    uint256 constant TOLERANCE = 1e15; // 0.1%, as forge-std counts relative deltas
    uint8 constant WETH_KIND = 0;
    uint8 constant WSTETH_KIND = 1;
    uint8 constant RETH_KIND = 2;
    bytes4 constant FETCH = IPriceFeed.fetchPrice.selector;
    bytes4 constant REDEEM = IPriceFeed.fetchRedemptionPrice.selector;

    MockFeed[3] ethUsdFeeds;
    MockFeed stEthUsd;
    MockFeed stEthEth;
    MockFeed wstEthUsd;
    MockFeed rEthEth;
    MockWstETH wstEth;
    MockStETH stEth;
    MockRETH rEth;

    // What the mocks show. USD feeds carry 8 decimals; ETH-quoted feeds and staking rates carry 18.
    int256 ethUsdPrice = 3000e8;
    int256 stEthUsdPrice = 3000e8;
    uint256 rEthEthPrice = 1.1e18;
    uint256 stEthPerToken = 1.2e18;
    uint256 rEthRate = 1.1e18;

    DeployPriceFeeds deployer;
    IPriceFeed weth;
    IPriceFeed wsteth;
    IPriceFeed reth;

    function setUp() public {
        vm.warp(1_800_000_000);
        vm.roll(24_000_000);
        ethUsdFeeds[0] = place(ETH_USD, 8, "ETH / USD");
        ethUsdFeeds[1] = place(ETH_USD_SVR, 8, "ETH / USD");
        ethUsdFeeds[2] = place(ETH_USD_SHARED_SVR, 8, "ETH / USD");
        stEthUsd = place(STETH_USD, 8, "STETH / USD");
        stEthEth = place(STETH_ETH, 18, "STETH / ETH");
        wstEthUsd = place(WSTETH_USD, 8, "WSTETH / USD");
        rEthEth = place(RETH_ETH, 18, "RETH / ETH");
        vm.etch(WSTETH, type(MockWstETH).runtimeCode);
        vm.etch(STETH, type(MockStETH).runtimeCode);
        vm.etch(RETH, type(MockRETH).runtimeCode);
        vm.label(WSTETH, "wstETH");
        vm.label(STETH, "stETH");
        vm.label(RETH, "rETH");
        wstEth = MockWstETH(WSTETH);
        stEth = MockStETH(STETH);
        rEth = MockRETH(RETH);
        wstEth.init(STETH, stEthPerToken);
        stEth.init(WSTETH);
        rEth.set(rEthRate);
        setEthUsd(ethUsdPrice, 0);
        setStEth(stEthUsdPrice, 0);
        setREthEth(rEthEthPrice, 0);
    }

    function place(address at, uint8 decimals, string memory description) internal returns (MockFeed feed) {
        vm.etch(at, type(MockFeed).runtimeCode);
        vm.label(at, description);
        feed = MockFeed(at);
        feed.init(decimals, description);
    }

    // Each check deploys from inside its own test function, the way `forge script` would run the
    // agent's script: msg.sender inside run(), a bare vm.startBroadcast() and a broadcast with
    // PRIVATE_KEY all act as the same account. The script sees mainnet's chain id, since the
    // instruction says mainnet and a script may refuse to run anywhere else.
    function deploy() internal {
        vm.chainId(1);
        deployer = new DeployPriceFeeds();
        vm.startBroadcast();
        (, address sender,) = vm.readCallers();
        vm.stopBroadcast();
        vm.etch(sender, type(Forwarder).runtimeCode);
        bytes memory result = Forwarder(sender).forward(address(deployer), abi.encodeCall(deployer.run, ()));
        vm.etch(sender, "");
        (address w, address s, address r) = abi.decode(result, (address, address, address));
        assertTrue(w.code.length > 0 && s.code.length > 0 && r.code.length > 0, "run() did not return three deployed feeds");
        weth = IPriceFeed(w);
        wsteth = IPriceFeed(s);
        reth = IPriceFeed(r);
        prime();
    }

    // One live fetch on every branch, so each feed has a last good price before anything breaks.
    function prime() internal {
        assertLive(weth, FETCH, usd(ethUsdPrice, 1e18), "WETH right after deployment");
        assertLive(wsteth, FETCH, usd(stEthUsdPrice, stEthPerToken), "wstETH right after deployment");
        assertLive(reth, FETCH, usd(ethUsdPrice, rEthEthPrice), "rETH right after deployment");
    }

    // Every change to a feed lands in a new block, as it would on mainnet.
    function nextBlock() internal {
        vm.warp(block.timestamp + BLOCK);
        vm.roll(block.number + 1);
    }

    function setEthUsd(int256 price, uint256 age) internal {
        nextBlock();
        ethUsdPrice = price;
        for (uint256 i; i < ethUsdFeeds.length; ++i) ethUsdFeeds[i].set(price, block.timestamp - age);
    }

    // The three stETH feeds move together, so a feed built on any of them sees the same market.
    function setStEth(int256 price, uint256 age) internal {
        nextBlock();
        stEthUsdPrice = price;
        stEthUsd.set(price, block.timestamp - age);
        stEthEth.set(price * 1e18 / ethUsdPrice, block.timestamp - age);
        wstEthUsd.set(price * int256(stEthPerToken) / 1e18, block.timestamp - age);
    }

    function setREthEth(uint256 price, uint256 age) internal {
        nextBlock();
        rEthEthPrice = price;
        rEthEth.set(int256(price), block.timestamp - age);
    }

    // An 8-decimal USD price times an 18-decimal rate, as an 18-decimal USD price.
    function usd(int256 price8, uint256 rate18) internal pure returns (uint256) {
        return uint256(price8) * 1e10 * rate18 / 1e18;
    }

    function call(IPriceFeed feed, bytes4 selector) internal returns (bool ok, uint256 price, bool broken) {
        (bool success, bytes memory data) = address(feed).call(abi.encodeWithSelector(selector));
        if (!success || data.length < 64) return (false, 0, false);
        (price, broken) = abi.decode(data, (uint256, bool));
        ok = true;
    }

    function within(uint256 price, uint256 expected) internal pure returns (bool) {
        uint256 delta = price > expected ? price - expected : expected - price;
        return delta * 1e18 <= expected * TOLERANCE;
    }

    function assertLive(IPriceFeed feed, bytes4 selector, uint256 expected, string memory what) internal {
        (bool ok, uint256 price, bool broken) = call(feed, selector);
        assertTrue(ok, string.concat(what, ": the call reverted"));
        assertFalse(broken, string.concat(what, ": a working oracle was reported broken"));
        assertApproxEqRel(price, expected, TOLERANCE, string.concat(what, ": wrong price"));
    }

    function test_pricesComeFromTheRightFeeds() public {
        deploy();
        assertLive(weth, REDEEM, 3000e18, "WETH redemption price at ETH/USD 3000");
        assertLive(wsteth, REDEEM, 3600e18, "wstETH redemption price at stETH/USD 3000 and 1.2 stETH per wstETH");
        assertLive(reth, REDEEM, 3300e18, "rETH redemption price at ETH/USD 3000 and rETH/ETH 1.1");
        setEthUsd(2500e8, 0);
        setStEth(2500e8, 0);
        assertLive(weth, FETCH, 2500e18, "WETH after ETH/USD moved to 2500");
        assertLive(wsteth, FETCH, 3000e18, "wstETH after stETH/USD moved to 2500");
        assertLive(reth, FETCH, 2750e18, "rETH after ETH/USD moved to 2500");
        setREthEth(1.08e18, 0);
        rEth.set(1.08e18);
        assertLive(reth, FETCH, 2700e18, "rETH after rETH/ETH and its staking rate moved to 1.08");
    }

    function test_stalenessFollowsEachFeed() public {
        deploy();
        // A branch that never reads its market feed answers to the LST check, not to this one.
        bool rEthReadsMarket = probe(RETH_KIND, 0);
        bool wstEthReadsMarket = probe(WSTETH_KIND, 0);
        // One block past the heartbeat is an ordinary update, not an outage.
        assertTrue(probe(WETH_KIND, 1 hours + BLOCK), "ETH/USD one block past its 1 h heartbeat was treated as stale");
        if (rEthReadsMarket) {
            assertTrue(probe(RETH_KIND, 1 days + BLOCK), "rETH/ETH one block past its 24 h heartbeat was treated as stale");
        }
        if (wstEthReadsMarket) {
            assertTrue(probe(WSTETH_KIND, 1 hours + BLOCK), "the stETH feeds one block past their heartbeat were treated as stale");
        }
        // Three days without an update is a dead feed.
        assertFalse(probe(WETH_KIND, 72 hours + 60), "a 72 h old ETH/USD price was accepted as live");
        if (rEthReadsMarket) assertFalse(probe(RETH_KIND, 72 hours + 60), "a 72 h old rETH/ETH price was accepted as live");
        if (wstEthReadsMarket) assertFalse(probe(WSTETH_KIND, 72 hours + 60), "72 h old stETH feeds were accepted as live");
        // Each threshold follows its own feed: the 24 h feed gets hours more room than the 1 h feed.
        if (!rEthReadsMarket) return;
        uint256 ethUsdThreshold = firstStaleAge(WETH_KIND, 1 hours + BLOCK);
        uint256 rEthEthThreshold = firstStaleAge(RETH_KIND, 1 days + BLOCK);
        assertGe(rEthEthThreshold, ethUsdThreshold + 1 hours, string.concat(
            "the rETH/ETH staleness threshold (", vm.toString(rEthEthThreshold),
            " s) is not at least an hour above ETH/USD's (", vm.toString(ethUsdThreshold),
            " s), so thresholds do not follow each feed's heartbeat"));
    }

    // Ages one feed, with an answer that differs from the last good price, and asks whether the
    // branch still treats it as live. The world is restored afterwards.
    function probe(uint8 kind, uint256 age) internal returns (bool live) {
        uint256 snapshot = vm.snapshotState();
        IPriceFeed feed;
        uint256 expected;
        if (kind == WETH_KIND) {
            setEthUsd(2900e8, age);
            feed = weth;
            expected = 2900e18;
        } else if (kind == RETH_KIND) {
            setREthEth(1.09e18, age);
            feed = reth;
            expected = usd(ethUsdPrice, 1.09e18);
        } else {
            setStEth(2950e8, age);
            feed = wsteth;
            expected = usd(2950e8, stEthPerToken);
        }
        (bool ok, uint256 price, bool broken) = call(feed, FETCH);
        live = ok && !broken && within(price, expected);
        assertTrue(vm.revertToState(snapshot), "snapshot restore failed");
    }

    // The smallest age, to the second, at which the branch stops treating the feed as live.
    function firstStaleAge(uint8 kind, uint256 lo) internal returns (uint256) {
        uint256 hi = 72 hours + 60;
        while (hi - lo > 1) {
            uint256 mid = (lo + hi) / 2;
            if (probe(kind, mid)) lo = mid;
            else hi = mid;
        }
        return hi;
    }

    function test_lstPriceFollowsTheMarketDownAndTheRateUp() public {
        deploy();
        uint256 snapshot = vm.snapshotState();
        setREthEth(1.15e18, 0);
        assertLive(reth, FETCH, usd(ethUsdPrice, rEthRate),
            "rETH with the market 4.5% above the staking rate, which must cap the price");
        assertTrue(vm.revertToState(snapshot), "snapshot restore failed");
        setREthEth(1.05e18, 0);
        assertLive(reth, FETCH, usd(ethUsdPrice, 1.05e18),
            "rETH with the market 4.5% below the staking rate, which the price must follow");
        assertTrue(vm.revertToState(snapshot), "snapshot restore failed");
        setStEth(2850e8, 0);
        assertLive(wsteth, FETCH, usd(2850e8, stEthPerToken),
            "wstETH with stETH 5% below ETH, which the price must follow");
    }

    function test_redemptionPriceProtectsBorrowers() public {
        deploy();
        (, uint256 wethPrice,) = call(weth, FETCH);
        (bool ok, uint256 wethRedemption, bool broken) = call(weth, REDEEM);
        assertTrue(ok && !broken, "WETH fetchRedemptionPrice failed");
        assertApproxEqRel(wethRedemption, wethPrice, TOLERANCE, "WETH redemption price differs from its price");
        // Both LSTs trade half a percent under their staking rate.
        setStEth(2985e8, 0);
        setREthEth(1.0945e18, 0);
        assertRedemptionLeansOnTheRate(wsteth, usd(ethUsdPrice, stEthPerToken), "wstETH");
        assertRedemptionLeansOnTheRate(reth, usd(ethUsdPrice, rEthRate), "rETH");
    }

    function assertRedemptionLeansOnTheRate(IPriceFeed feed, uint256 rateValue, string memory name) internal {
        (bool ok, uint256 price, bool broken) = call(feed, FETCH);
        assertTrue(ok && !broken, string.concat(name, " fetchPrice failed on a 0.5% discount"));
        (bool okRedemption, uint256 redemption, bool brokenRedemption) = call(feed, REDEEM);
        assertTrue(okRedemption && !brokenRedemption, string.concat(name, " fetchRedemptionPrice failed on a 0.5% discount"));
        assertGe(redemption, price, string.concat(name, " redemption price is below the borrowing price"));
        assertApproxEqRel(redemption, rateValue, TOLERANCE,
            string.concat(name, " redemption price does not lean on the staking rate when the market trades 0.5% under it"));
    }

    function test_brokenFeedKeepsTheBranchLiquidatable() public {
        deploy();
        setEthUsd(3100e8, 0);
        assertLive(weth, FETCH, 3100e18, "WETH before the outage");
        assertLive(reth, FETCH, usd(3100e8, rEthRate), "rETH before the outage");
        uint256 snapshot = vm.snapshotState();

        for (uint256 i; i < ethUsdFeeds.length; ++i) ethUsdFeeds[i].setFailing(true);
        nextBlock();
        assertDegraded(weth, 3100e18, "WETH after ETH/USD started reverting");
        assertTrue(vm.revertToState(snapshot), "snapshot restore failed");

        setEthUsd(0, 0);
        assertDegraded(weth, 3100e18, "WETH after ETH/USD answered 0");
        assertTrue(vm.revertToState(snapshot), "snapshot restore failed");

        setEthUsd(-1, 0);
        assertDegraded(weth, 3100e18, "WETH after ETH/USD answered a negative price");
        assertTrue(vm.revertToState(snapshot), "snapshot restore failed");

        setEthUsd(2000e8, 73 hours);
        assertDegraded(weth, 3100e18, "WETH after ETH/USD went 73 h without an update");
        assertTrue(vm.revertToState(snapshot), "snapshot restore failed");

        // The LST market feed dies while ETH/USD and the staking rate keep working.
        setEthUsd(3200e8, 0);
        rEthEth.setFailing(true);
        (bool ok, uint256 price, bool broken) = call(reth, FETCH);
        assertTrue(ok, "rETH fetchPrice reverted when rETH/ETH started reverting, so liquidations and closes would be stuck");
        assertTrue(broken, "rETH did not report the rETH/ETH outage");
        assertTrue(within(price, usd(3100e8, rEthRate)) || within(price, usd(3200e8, rEthRate)),
            "rETH price after its market feed broke is neither the last good price nor ETH/USD times the staking rate");
        (ok, price,) = call(reth, FETCH);
        assertTrue(ok, "rETH second fetchPrice after the outage reverted");
        assertTrue(within(price, usd(3100e8, rEthRate)) || within(price, usd(3200e8, rEthRate)),
            "rETH second price after the outage is neither the last good price nor ETH/USD times the staking rate");
    }

    function assertDegraded(IPriceFeed feed, uint256 lastGood, string memory what) internal {
        (bool ok, uint256 price, bool broken) = call(feed, FETCH);
        assertTrue(ok, string.concat(what, ": fetchPrice reverted, so liquidations and closes would be stuck"));
        assertTrue(broken, string.concat(what, ": the outage was not reported"));
        assertApproxEqRel(price, lastGood, TOLERANCE, string.concat(what, ": the price is not the last good price"));
        (ok, price,) = call(feed, FETCH);
        assertTrue(ok, string.concat(what, ": the next fetchPrice reverted"));
        assertApproxEqRel(price, lastGood, TOLERANCE, string.concat(what, ": the next price is not the last good price"));
        (ok, price,) = call(feed, REDEEM);
        assertTrue(ok, string.concat(what, ": fetchRedemptionPrice reverted"));
        assertApproxEqRel(price, lastGood, TOLERANCE, string.concat(what, ": the redemption price is not the last good price"));
    }

    function test_lowGasCannotFakeAnOutage() public {
        deploy();
        int256 price = 3050e8;
        setEthUsd(price, 0);
        // A slow feed makes the gas boundary wide enough to land on. A design that caps the gas of its
        // oracle call sees a slower feed as down, so the feed is only made as slow as the design allows.
        uint256 burn = feedGasBudget(3_000_000);
        for (uint256 i; i < ethUsdFeeds.length; ++i) ethUsdFeeds[i].setBurnGas(burn);
        assertLive(weth, FETCH, usd(price, 1e18), "WETH with a slow ETH/USD feed");
        for (uint256 gas = 1_000_000; gas <= 3_400_000; gas += 50_000) {
            // The price moves first, so a branch stuck on its last good price shows.
            price += 1e8;
            setEthUsd(price, 0);
            (bool reverted,) = address(weth).call{gas: gas}(abi.encodeWithSelector(FETCH));
            reverted;
            // Whatever that call did, the oracle is fine, and the next caller must see the live price.
            (bool ok, uint256 live, bool broken) = call(weth, FETCH);
            string memory what = string.concat("after a fetchPrice call with ", vm.toString(gas), " gas");
            assertTrue(ok, string.concat(what, ": the next fetchPrice reverted"));
            assertFalse(broken, string.concat(what, ": the next fetchPrice reported the oracle broken"));
            assertApproxEqRel(live, usd(price, 1e18), TOLERANCE, string.concat(what, ": the next fetchPrice did not return the live price"));
        }
    }

    // How much gas the ETH/USD feed may spend before a normal fetchPrice call reports it down, up to
    // `ceiling`. A design that forwards all its gas gets the ceiling; a design that caps the call gets
    // nine tenths of the largest spend it still accepts, found by binary search to within 10k gas.
    function feedGasBudget(uint256 ceiling) internal returns (uint256) {
        if (liveWithBurn(ceiling)) return ceiling;
        uint256 lo = 0;
        uint256 hi = ceiling;
        while (hi - lo > 10_000) {
            uint256 mid = (lo + hi) / 2;
            if (liveWithBurn(mid)) lo = mid;
            else hi = mid;
        }
        return lo * 9 / 10;
    }

    function liveWithBurn(uint256 burn) internal returns (bool live) {
        uint256 snapshot = vm.snapshotState();
        for (uint256 i; i < ethUsdFeeds.length; ++i) ethUsdFeeds[i].setBurnGas(burn);
        (bool ok, uint256 price, bool broken) = call(weth, FETCH);
        live = ok && !broken && within(price, usd(ethUsdPrice, 1e18));
        assertTrue(vm.revertToState(snapshot), "snapshot restore failed");
    }
}
