#!/bin/sh
set -eu
root=${WORKSPACE:-/workspace}
mkdir -p "$root/src/PriceFeeds" "$root/script"
cat > "$root/src/PriceFeeds/AggregatorV3Interface.sol" <<'SOL'
// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

interface AggregatorV3Interface {
    function decimals() external view returns (uint8);
    function latestRoundData()
        external
        view
        returns (uint80 roundId, int256 answer, uint256 startedAt, uint256 updatedAt, uint80 answeredInRound);
}
SOL
cat > "$root/src/PriceFeeds/PriceFeedBase.sol" <<'SOL'
// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {IPriceFeed} from "../interfaces/IPriceFeed.sol";
import {AggregatorV3Interface} from "./AggregatorV3Interface.sol";

/// Chainlink plumbing shared by every branch, after Liquity V2's MainnetPriceFeedBase.
abstract contract PriceFeedBase is IPriceFeed {
    enum PriceSource {
        primary,
        ethUsdTimesRate,
        lastGoodPrice
    }

    struct Oracle {
        AggregatorV3Interface aggregator;
        uint256 stalenessThreshold;
        uint8 decimals;
    }

    struct Response {
        int256 answer;
        uint256 updatedAt;
        bool success;
    }

    error InsufficientGasForExternalCall();

    event OracleFailure(address oracle);

    PriceSource public priceSource;
    uint256 public lastGoodPrice;
    Oracle public ethUsdOracle;

    constructor(address ethUsdAggregator, uint256 ethUsdStalenessThreshold) {
        ethUsdOracle = _oracle(ethUsdAggregator, ethUsdStalenessThreshold);
        require(ethUsdOracle.decimals == 8, "ETH/USD feed must have 8 decimals");
    }

    function _oracle(address aggregator, uint256 stalenessThreshold) internal view returns (Oracle memory oracle) {
        oracle.aggregator = AggregatorV3Interface(aggregator);
        oracle.stalenessThreshold = stalenessThreshold;
        oracle.decimals = oracle.aggregator.decimals();
    }

    /// Reads one feed. Returns its answer with 18 decimals, and whether the feed is unusable.
    function _read(Oracle memory oracle) internal view returns (uint256 price, bool down) {
        Response memory response = _latestRoundData(oracle.aggregator);
        bool fresh = response.updatedAt <= block.timestamp
            && block.timestamp - response.updatedAt < oracle.stalenessThreshold;
        if (!response.success || response.answer <= 0 || !fresh) return (0, true);
        return (uint256(response.answer) * 10 ** (18 - oracle.decimals), false);
    }

    function _latestRoundData(AggregatorV3Interface aggregator) internal view returns (Response memory response) {
        uint256 gasBefore = gasleft();
        try aggregator.latestRoundData() returns (uint80, int256 answer, uint256, uint256 updatedAt, uint80) {
            return Response(answer, updatedAt, true);
        } catch {
            // A call that ran out of gas inside the feed says nothing about the feed. Revert instead
            // of recording an outage.
            if (gasleft() <= gasBefore / 64) revert InsufficientGasForExternalCall();
            return response;
        }
    }

    function _switchToLastGoodPrice(address failed) internal returns (uint256) {
        priceSource = PriceSource.lastGoodPrice;
        emit OracleFailure(failed);
        return lastGoodPrice;
    }
}
SOL
cat > "$root/src/PriceFeeds/WETHPriceFeed.sol" <<'SOL'
// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {PriceFeedBase} from "./PriceFeedBase.sol";

contract WETHPriceFeed is PriceFeedBase {
    constructor(address ethUsdAggregator, uint256 ethUsdStalenessThreshold)
        PriceFeedBase(ethUsdAggregator, ethUsdStalenessThreshold)
    {
        _fetchPrimary();
        require(priceSource == PriceSource.primary, "ETH/USD feed is down");
    }

    function fetchPrice() public returns (uint256, bool) {
        if (priceSource == PriceSource.primary) return _fetchPrimary();
        return (lastGoodPrice, false);
    }

    function fetchRedemptionPrice() external returns (uint256, bool) {
        return fetchPrice();
    }

    function _fetchPrimary() internal returns (uint256, bool) {
        (uint256 ethUsdPrice, bool down) = _read(ethUsdOracle);
        if (down) return (_switchToLastGoodPrice(address(ethUsdOracle.aggregator)), true);
        lastGoodPrice = ethUsdPrice;
        return (ethUsdPrice, false);
    }
}
SOL
cat > "$root/src/PriceFeeds/CompositePriceFeed.sol" <<'SOL'
// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {PriceFeedBase} from "./PriceFeedBase.sol";

/// A branch whose collateral is an LST: a market price and the token's own staking rate.
abstract contract CompositePriceFeed is PriceFeedBase {
    address public immutable rateProvider;

    constructor(address ethUsdAggregator, address rateProvider_, uint256 ethUsdStalenessThreshold)
        PriceFeedBase(ethUsdAggregator, ethUsdStalenessThreshold)
    {
        rateProvider = rateProvider_;
    }

    function fetchPrice() public returns (uint256, bool) {
        if (priceSource == PriceSource.primary) return _fetchPrimary(false);
        return _fetchDuringShutdown();
    }

    function fetchRedemptionPrice() external returns (uint256, bool) {
        if (priceSource == PriceSource.primary) return _fetchPrimary(true);
        return _fetchDuringShutdown();
    }

    /// The LST's market feed failed but ETH/USD works: price it from ETH/USD and the staking rate.
    function _switchToEthUsdTimesRate(address failed, uint256 ethUsdPrice) internal returns (uint256) {
        priceSource = PriceSource.ethUsdTimesRate;
        emit OracleFailure(failed);
        return _ethUsdTimesRate(ethUsdPrice);
    }

    function _fetchDuringShutdown() internal returns (uint256, bool) {
        if (priceSource == PriceSource.ethUsdTimesRate) {
            (uint256 ethUsdPrice, bool down) = _read(ethUsdOracle);
            if (down) {
                priceSource = PriceSource.lastGoodPrice;
                return (lastGoodPrice, false);
            }
            return (_ethUsdTimesRate(ethUsdPrice), false);
        }
        return (lastGoodPrice, false);
    }

    function _ethUsdTimesRate(uint256 ethUsdPrice) internal returns (uint256) {
        (uint256 rate, bool down) = _canonicalRate();
        if (down) {
            priceSource = PriceSource.lastGoodPrice;
            return lastGoodPrice;
        }
        uint256 rateValue = ethUsdPrice * rate / 1e18;
        uint256 price = rateValue < lastGoodPrice ? rateValue : lastGoodPrice;
        lastGoodPrice = price;
        return price;
    }

    function _withinDeviation(uint256 price, uint256 anchor, uint256 deviation) internal pure returns (bool) {
        uint256 upper = anchor * (1e18 + deviation) / 1e18;
        uint256 lower = anchor * (1e18 - deviation) / 1e18;
        return price >= lower && price <= upper;
    }

    function _max(uint256 a, uint256 b) internal pure returns (uint256) {
        return a > b ? a : b;
    }

    function _min(uint256 a, uint256 b) internal pure returns (uint256) {
        return a < b ? a : b;
    }

    function _fetchPrimary(bool isRedemption) internal virtual returns (uint256, bool);

    function _canonicalRate() internal view virtual returns (uint256, bool);
}
SOL
cat > "$root/src/PriceFeeds/WSTETHPriceFeed.sol" <<'SOL'
// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {CompositePriceFeed} from "./CompositePriceFeed.sol";

interface IWstETH {
    function stEthPerToken() external view returns (uint256);
}

contract WSTETHPriceFeed is CompositePriceFeed {
    /// Redemptions take the higher of stETH/USD and ETH/USD while the two are this close.
    uint256 public constant STETH_USD_DEVIATION_THRESHOLD = 1e16;

    Oracle public stEthUsdOracle;

    constructor(
        address ethUsdAggregator,
        address stEthUsdAggregator,
        address wstEth,
        uint256 ethUsdStalenessThreshold,
        uint256 stEthUsdStalenessThreshold
    ) CompositePriceFeed(ethUsdAggregator, wstEth, ethUsdStalenessThreshold) {
        stEthUsdOracle = _oracle(stEthUsdAggregator, stEthUsdStalenessThreshold);
        require(stEthUsdOracle.decimals == 8, "stETH/USD feed must have 8 decimals");
        _fetchPrimary(false);
        require(priceSource == PriceSource.primary, "an oracle is down");
    }

    function _fetchPrimary(bool isRedemption) internal override returns (uint256, bool) {
        (uint256 stEthUsdPrice, bool stEthUsdDown) = _read(stEthUsdOracle);
        (uint256 stEthPerWstEth, bool rateDown) = _canonicalRate();
        (uint256 ethUsdPrice, bool ethUsdDown) = _read(ethUsdOracle);
        // The rate is in every price, and ETH/USD is in the fallback and in redemptions.
        if (rateDown) return (_switchToLastGoodPrice(rateProvider), true);
        if (ethUsdDown) return (_switchToLastGoodPrice(address(ethUsdOracle.aggregator)), true);
        if (stEthUsdDown) return (_switchToEthUsdTimesRate(address(stEthUsdOracle.aggregator), ethUsdPrice), true);

        uint256 stEthPrice = stEthUsdPrice;
        if (isRedemption && _withinDeviation(stEthUsdPrice, ethUsdPrice, STETH_USD_DEVIATION_THRESHOLD)) {
            stEthPrice = _max(stEthUsdPrice, ethUsdPrice);
        }
        uint256 price = stEthPrice * stEthPerWstEth / 1e18;
        lastGoodPrice = price;
        return (price, false);
    }

    function _canonicalRate() internal view override returns (uint256, bool) {
        uint256 gasBefore = gasleft();
        try IWstETH(rateProvider).stEthPerToken() returns (uint256 rate) {
            return (rate, rate == 0);
        } catch {
            if (gasleft() <= gasBefore / 64) revert InsufficientGasForExternalCall();
            return (0, true);
        }
    }
}
SOL
cat > "$root/src/PriceFeeds/RETHPriceFeed.sol" <<'SOL'
// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {CompositePriceFeed} from "./CompositePriceFeed.sol";

interface IRETH {
    function getExchangeRate() external view returns (uint256);
}

contract RETHPriceFeed is CompositePriceFeed {
    /// Redemptions take the higher of the market and the staking rate while the two are this close.
    uint256 public constant RETH_ETH_DEVIATION_THRESHOLD = 2e16;

    Oracle public rEthEthOracle;

    constructor(
        address ethUsdAggregator,
        address rEthEthAggregator,
        address rEth,
        uint256 ethUsdStalenessThreshold,
        uint256 rEthEthStalenessThreshold
    ) CompositePriceFeed(ethUsdAggregator, rEth, ethUsdStalenessThreshold) {
        rEthEthOracle = _oracle(rEthEthAggregator, rEthEthStalenessThreshold);
        require(rEthEthOracle.decimals == 18, "rETH/ETH feed must have 18 decimals");
        _fetchPrimary(false);
        require(priceSource == PriceSource.primary, "an oracle is down");
    }

    function _fetchPrimary(bool isRedemption) internal override returns (uint256, bool) {
        (uint256 ethUsdPrice, bool ethUsdDown) = _read(ethUsdOracle);
        (uint256 rEthEthPrice, bool rEthEthDown) = _read(rEthEthOracle);
        (uint256 ethPerREth, bool rateDown) = _canonicalRate();
        if (ethUsdDown) return (_switchToLastGoodPrice(address(ethUsdOracle.aggregator)), true);
        if (rateDown) return (_switchToLastGoodPrice(rateProvider), true);
        if (rEthEthDown) return (_switchToEthUsdTimesRate(address(rEthEthOracle.aggregator), ethUsdPrice), true);

        uint256 marketPrice = ethUsdPrice * rEthEthPrice / 1e18;
        uint256 rateValue = ethUsdPrice * ethPerREth / 1e18;
        uint256 price;
        if (isRedemption && _withinDeviation(marketPrice, rateValue, RETH_ETH_DEVIATION_THRESHOLD)) {
            price = _max(marketPrice, rateValue);
        } else {
            // The lower of the two, so neither a tilted pool nor a tampered rate inflates collateral.
            price = _min(marketPrice, rateValue);
        }
        lastGoodPrice = price;
        return (price, false);
    }

    function _canonicalRate() internal view override returns (uint256, bool) {
        uint256 gasBefore = gasleft();
        try IRETH(rateProvider).getExchangeRate() returns (uint256 rate) {
            return (rate, rate == 0);
        } catch {
            if (gasleft() <= gasBefore / 64) revert InsufficientGasForExternalCall();
            return (0, true);
        }
    }
}
SOL
cat > "$root/script/DeployPriceFeeds.s.sol" <<'SOL'
// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {Script} from "forge-std/Script.sol";
import {WETHPriceFeed} from "../src/PriceFeeds/WETHPriceFeed.sol";
import {WSTETHPriceFeed} from "../src/PriceFeeds/WSTETHPriceFeed.sol";
import {RETHPriceFeed} from "../src/PriceFeeds/RETHPriceFeed.sol";

contract DeployPriceFeeds is Script {
    // Chainlink proxies on mainnet.
    address constant ETH_USD = 0x5f4eC3Df9cbd43714FE2740f5E3616155c5b8419;
    address constant STETH_USD = 0xCfE54B5cD566aB89272946F602D76Ea879CAb4a8;
    address constant RETH_ETH = 0x536218f9E9Eb48863970252233c8F271f554C2d0;
    // The LST tokens, for their staking rates.
    address constant WSTETH = 0x7f39C581F595B53c5cb19bD0b3f8dA6c935E2Ca0;
    address constant RETH = 0xae78736Cd615f374D3085123A210448E74Fc6393;
    // Each threshold leaves room past its feed's heartbeat: 1 h for the USD feeds, 24 h for rETH/ETH.
    uint256 constant ETH_USD_STALENESS = 24 hours;
    uint256 constant STETH_USD_STALENESS = 24 hours;
    uint256 constant RETH_ETH_STALENESS = 48 hours;

    function run() external returns (address wethFeed, address wstEthFeed, address rEthFeed) {
        vm.startBroadcast();
        wethFeed = address(new WETHPriceFeed(ETH_USD, ETH_USD_STALENESS));
        wstEthFeed = address(new WSTETHPriceFeed(ETH_USD, STETH_USD, WSTETH, ETH_USD_STALENESS, STETH_USD_STALENESS));
        rEthFeed = address(new RETHPriceFeed(ETH_USD, RETH_ETH, RETH, ETH_USD_STALENESS, RETH_ETH_STALENESS));
        vm.stopBroadcast();
    }
}
SOL
