#!/bin/sh
set -eu
mkdir -p /workspace/src
cat > /workspace/src/RevenuePayouts.sol <<'SOL'
// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

interface IERC20Balance {
    function balanceOf(address account) external view returns (uint256);
}

contract RevenuePayouts {
    mapping(address => uint256) private shares;
    uint256 private totalShares;
    uint256 private totalReleased;
    mapping(address => uint256) private released;
    mapping(address => uint256) private tokenTotalReleased;
    mapping(address => mapping(address => uint256)) private tokenReleased;

    constructor(address[] memory payees, uint256[] memory weights) {
        require(payees.length != 0 && payees.length == weights.length, "lists");
        for (uint256 i; i < payees.length; ++i) {
            require(payees[i] != address(0) && weights[i] != 0, "payee");
            require(shares[payees[i]] == 0, "duplicate");
            shares[payees[i]] = weights[i];
            totalShares += weights[i];
        }
    }

    receive() external payable {}

    function release(address payee) external {
        require(shares[payee] != 0, "payee");
        uint256 payment = (address(this).balance + totalReleased)
            * shares[payee] / totalShares - released[payee];
        require(payment != 0, "nothing due");
        released[payee] += payment;
        totalReleased += payment;
        (bool ok,) = payable(payee).call{value: payment}("");
        require(ok, "ETH payment");
    }

    function release(address token, address payee) external {
        require(shares[payee] != 0, "payee");
        uint256 received = IERC20Balance(token).balanceOf(address(this)) + tokenTotalReleased[token];
        uint256 payment = received * shares[payee] / totalShares - tokenReleased[token][payee];
        require(payment != 0, "nothing due");
        tokenReleased[token][payee] += payment;
        tokenTotalReleased[token] += payment;
        (bool ok, bytes memory data) = token.call(
            abi.encodeWithSignature("transfer(address,uint256)", payee, payment)
        );
        require(ok && (data.length == 0 || abi.decode(data, (bool))), "token payment");
    }
}
SOL
