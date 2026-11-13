// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

/// Stands in for a Chainlink proxy at a mainnet feed address, with the whole AggregatorV2V3Interface.
/// The tests etch it, so it has no constructor; `init` takes the constructor's place.
contract MockFeed {
    uint8 public decimals;
    string public description;
    uint80 public latestRound;
    bool public failing;
    uint256 public burnGas;
    mapping(uint80 => int256) private answers;
    mapping(uint80 => uint256) private updates;

    function init(uint8 decimals_, string memory description_) external {
        decimals = decimals_;
        description = description_;
    }

    function set(int256 answer, uint256 updatedAt) external {
        latestRound += 1;
        answers[latestRound] = answer;
        updates[latestRound] = updatedAt;
    }

    function setFailing(bool failing_) external {
        failing = failing_;
    }

    function setBurnGas(uint256 amount) external {
        burnGas = amount;
    }

    function version() external pure returns (uint256) {
        return 6;
    }

    function aggregator() external view returns (address) {
        return address(this);
    }

    function phaseId() external pure returns (uint16) {
        return 1;
    }

    function phaseAggregators(uint16) external view returns (address) {
        return address(this);
    }

    function minAnswer() external pure returns (int192) {
        return 1;
    }

    function maxAnswer() external pure returns (int192) {
        return type(int192).max;
    }

    function latestRoundData() external view returns (uint80, int256, uint256, uint256, uint80) {
        burn();
        require(!failing, "feed down");
        return (latestRound, answers[latestRound], updates[latestRound], updates[latestRound], latestRound);
    }

    function getRoundData(uint80 round) external view returns (uint80, int256, uint256, uint256, uint80) {
        require(!failing, "feed down");
        return (round, answers[round], updates[round], updates[round], round);
    }

    function latestAnswer() external view returns (int256) {
        burn();
        require(!failing, "feed down");
        return answers[latestRound];
    }

    function latestTimestamp() external view returns (uint256) {
        require(!failing, "feed down");
        return updates[latestRound];
    }

    function getAnswer(uint256 round) external view returns (int256) {
        require(!failing, "feed down");
        return answers[uint80(round)];
    }

    function getTimestamp(uint256 round) external view returns (uint256) {
        require(!failing, "feed down");
        return updates[uint80(round)];
    }

    /// Spends `burnGas` before answering, so a test can make the feed as slow as it likes.
    function burn() internal view {
        uint256 stop = gasleft() > burnGas ? gasleft() - burnGas : 0;
        uint256 i;
        while (gasleft() > stop) {
            unchecked {
                ++i;
            }
        }
    }
}

/// Lido's wstETH token at its mainnet address: the rate views Liquity, Aave and Euler read.
contract MockWstETH {
    uint256 public stEthPerToken;
    address public stETH;

    function init(address stEth, uint256 rate) external {
        stETH = stEth;
        stEthPerToken = rate;
    }

    function set(uint256 rate) external {
        stEthPerToken = rate;
    }

    function tokensPerStEth() external view returns (uint256) {
        return 1e36 / stEthPerToken;
    }

    function getStETHByWstETH(uint256 wstEthAmount) external view returns (uint256) {
        return wstEthAmount * stEthPerToken / 1e18;
    }

    function getWstETHByStETH(uint256 stEthAmount) external view returns (uint256) {
        return stEthAmount * 1e18 / stEthPerToken;
    }

    function decimals() external pure returns (uint8) {
        return 18;
    }
}

/// Lido's stETH token at its mainnet address. Its share rate is wstETH's rate, so the two agree.
contract MockStETH {
    address public wstETH;

    function init(address wstEth) external {
        wstETH = wstEth;
    }

    function rate() internal view returns (uint256) {
        return MockWstETH(wstETH).stEthPerToken();
    }

    function getPooledEthByShares(uint256 shares) external view returns (uint256) {
        return shares * rate() / 1e18;
    }

    function getSharesByPooledEth(uint256 pooledEth) external view returns (uint256) {
        return pooledEth * 1e18 / rate();
    }

    function getTotalShares() external pure returns (uint256) {
        return 8_000_000e18;
    }

    function getTotalPooledEther() external view returns (uint256) {
        return 8_000_000e18 * rate() / 1e18;
    }

    function decimals() external pure returns (uint8) {
        return 18;
    }
}

/// Rocket Pool's rETH token at its mainnet address.
contract MockRETH {
    uint256 public exchangeRate;

    function set(uint256 rate) external {
        exchangeRate = rate;
    }

    function getExchangeRate() external view returns (uint256) {
        return exchangeRate;
    }

    function getEthValue(uint256 rEthAmount) external view returns (uint256) {
        return rEthAmount * exchangeRate / 1e18;
    }

    function getRethValue(uint256 ethAmount) external view returns (uint256) {
        return ethAmount * 1e18 / exchangeRate;
    }

    function decimals() external pure returns (uint8) {
        return 18;
    }
}
