// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

contract FixedPriceFeed {
    int256 private immutable answer;
    uint8 public immutable decimals;

    constructor(int256 price, uint8 feedDecimals) {
        answer = price;
        decimals = feedDecimals;
    }

    function latestAnswer() external view returns (int256) {
        return answer;
    }

    function latestRoundData() external view returns (uint80, int256, uint256, uint256, uint80) {
        return (1, answer, block.timestamp, block.timestamp, 1);
    }

    function description() external pure returns (string memory) {
        return "WETH / USD";
    }

    function version() external pure returns (uint256) {
        return 1;
    }
}
