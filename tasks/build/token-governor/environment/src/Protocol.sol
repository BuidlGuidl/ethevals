// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

contract Protocol {
    address public owner = msg.sender;
    uint256 public fee;

    modifier onlyOwner() {
        require(msg.sender == owner, "only owner");
        _;
    }

    function transferOwnership(address newOwner) external onlyOwner {
        require(newOwner != address(0), "zero owner");
        owner = newOwner;
    }

    function setFee(uint256 newFee) external onlyOwner {
        fee = newFee;
    }
}
