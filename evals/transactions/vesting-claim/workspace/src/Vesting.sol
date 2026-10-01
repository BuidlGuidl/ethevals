// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

interface IERC20 {
    function balanceOf(address account) external view returns (uint256);
    function transfer(address to, uint256 amount) external returns (bool);
}

contract Vesting {
    address public immutable owner;
    address public immutable beneficiary;
    uint64 public immutable start;
    uint64 public immutable duration;
    uint256 public released;
    mapping(address => uint256) public releasedTokens;

    constructor(address beneficiary_, uint64 start_, uint64 duration_) {
        require(beneficiary_ != address(0), "Beneficiary is zero");
        owner = msg.sender;
        beneficiary = beneficiary_;
        start = start_;
        duration = duration_;
    }

    modifier authorized() {
        require(msg.sender == owner || msg.sender == beneficiary, "Caller is not owner or beneficiary");
        _;
    }

    receive() external payable {}

    function vestedAmount(uint256 total) public view returns (uint256) {
        if (block.timestamp < start) return 0;
        if (block.timestamp >= uint256(start) + duration) return total;
        return total * (block.timestamp - start) / duration;
    }

    function release() external authorized {
        uint256 amount = vestedAmount(address(this).balance + released) - released;
        released += amount;
        (bool success,) = beneficiary.call{value: amount}("");
        require(success, "ETH transfer failed");
    }

    function release(address token) external authorized {
        uint256 amount = vestedAmount(IERC20(token).balanceOf(address(this)) + releasedTokens[token])
            - releasedTokens[token];
        releasedTokens[token] += amount;
        require(IERC20(token).transfer(beneficiary, amount), "Token transfer failed");
    }
}
