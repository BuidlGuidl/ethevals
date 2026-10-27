#!/bin/sh
set -eu
mkdir -p /workspace/src
cat > /workspace/src/Launchpad.sol <<'SOL'
// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

interface LaunchFactory {
    function getPair(address, address) external view returns (address);
    function createPair(address, address) external returns (address);
}

interface LaunchWETH {
    function deposit() external payable;
    function transfer(address, uint256) external returns (bool);
    function balanceOf(address) external view returns (uint256);
}

interface LaunchPair {
    function mint(address) external returns (uint256);
}

contract CommunityToken {
    string public name;
    string public symbol;
    uint8 public constant decimals = 18;
    uint256 public constant totalSupply = 1_000_000_000 ether;
    address public immutable issuer;
    address public immutable pool;
    bool public unlocked;
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    event Transfer(address indexed from, address indexed to, uint256 amount);
    event Approval(address indexed owner, address indexed spender, uint256 amount);

    constructor(string memory label, string memory ticker, address factory, address weth) {
        name = label;
        symbol = ticker;
        issuer = msg.sender;
        (address a, address b) = address(this) < weth ? (address(this), weth) : (weth, address(this));
        pool = address(uint160(uint256(keccak256(abi.encodePacked(
            hex"ff", factory, keccak256(abi.encodePacked(a, b)),
            hex"96e8ac4277198ff8b6f785478aa9a39f403cb768dd02cbee326c3e7da348845f"
        )))));
        balanceOf[issuer] = totalSupply;
        emit Transfer(address(0), issuer, totalSupply);
    }

    function unlock() external {
        require(msg.sender == issuer, "issuer only");
        unlocked = true;
    }

    function approve(address spender, uint256 amount) external returns (bool) {
        allowance[msg.sender][spender] = amount;
        emit Approval(msg.sender, spender, amount);
        return true;
    }

    function transfer(address to, uint256 amount) external returns (bool) {
        move(msg.sender, to, amount);
        return true;
    }

    function transferFrom(address from, address to, uint256 amount) external returns (bool) {
        uint256 approved = allowance[from][msg.sender];
        if (approved != type(uint256).max) allowance[from][msg.sender] = approved - amount;
        move(from, to, amount);
        return true;
    }

    function move(address from, address to, uint256 amount) private {
        require(to != address(0), "zero recipient");
        require(unlocked || to != pool, "pool locked");
        balanceOf[from] -= amount;
        balanceOf[to] += amount;
        emit Transfer(from, to, amount);
    }
}

contract Launchpad {
    address private constant FACTORY = 0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f;
    address private constant WETH = 0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2;
    address private constant BURN = 0x000000000000000000000000000000000000dEaD;
    uint256 private constant VIRTUAL = 4 ether;
    uint256 private constant TARGET = 10 ether;

    struct Market {
        address creator;
        bool migrated;
        uint256 funds;
        uint256 inventory;
        uint256 pendingFees;
    }

    mapping(address => Market) private markets;
    bool private entered;

    modifier guarded() {
        require(!entered, "reentry");
        entered = true;
        _;
        entered = false;
    }

    function create(string calldata name, string calldata symbol) external returns (address token) {
        token = address(new CommunityToken(name, symbol, FACTORY, WETH));
        markets[token] = Market(msg.sender, false, 0, CommunityToken(token).totalSupply(), 0);
    }

    function buy(address token) external payable guarded {
        Market storage m = markets[token];
        require(m.creator != address(0) && !m.migrated && m.funds < TARGET, "curve closed");
        require(msg.value != 0, "empty buy");
        uint256 net = msg.value - msg.value / 100;
        uint256 charged = msg.value;
        if (net > TARGET - m.funds) {
            net = TARGET - m.funds;
            charged = (net * 100 + 98) / 99;
        }
        uint256 fee = charged - net;
        uint256 tokens = m.inventory * net / (VIRTUAL + m.funds + net);
        require(tokens != 0, "empty output");
        m.funds += net;
        m.inventory -= tokens;
        m.pendingFees += fee;
        CommunityToken(token).transfer(msg.sender, tokens);
        if (charged < msg.value) pay(msg.sender, msg.value - charged);
    }

    function sell(address token, uint256 amount) external guarded {
        Market storage m = markets[token];
        require(m.creator != address(0) && !m.migrated && m.funds < TARGET, "curve closed");
        require(amount != 0, "empty sale");
        uint256 gross = (VIRTUAL + m.funds) * amount / (m.inventory + amount);
        require(gross != 0 && gross <= m.funds, "sale exceeds reserve");
        uint256 fee = gross / 100;
        m.funds -= gross;
        m.inventory += amount;
        m.pendingFees += fee;
        CommunityToken(token).transferFrom(msg.sender, address(this), amount);
        pay(msg.sender, gross - fee);
    }

    function claimFees(address token) external guarded {
        Market storage m = markets[token];
        require(msg.sender == m.creator, "creator only");
        uint256 due = m.pendingFees;
        m.pendingFees = 0;
        pay(m.creator, due);
    }

    function graduate(address token) external guarded {
        Market storage m = markets[token];
        require(m.creator != address(0) && !m.migrated && m.funds >= TARGET, "not ready");
        m.migrated = true;
        address pair = LaunchFactory(FACTORY).getPair(token, WETH);
        if (pair == address(0)) pair = LaunchFactory(FACTORY).createPair(token, WETH);
        require(pair == CommunityToken(token).pool(), "unexpected pair");
        uint256 funds = m.funds;
        LaunchWETH(WETH).deposit{value: funds}();
        require(LaunchWETH(WETH).transfer(pair, funds), "WETH transfer");
        // Donations cannot choose the price. Include their WETH when sizing the token side.
        uint256 tokens = LaunchWETH(WETH).balanceOf(pair) * m.inventory / (VIRTUAL + funds);
        require(tokens <= m.inventory, "donation exceeds inventory");
        m.funds = 0;
        m.inventory -= tokens;
        CommunityToken(token).unlock();
        CommunityToken(token).transfer(pair, tokens);
        LaunchPair(pair).mint(BURN);
    }

    function pay(address recipient, uint256 amount) private {
        (bool sent,) = payable(recipient).call{value: amount}("");
        require(sent, "ETH transfer");
    }
}
SOL
