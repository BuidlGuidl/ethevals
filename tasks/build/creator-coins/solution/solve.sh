#!/bin/sh
set -eu
mkdir -p /workspace/src
cat > /workspace/src/CreatorCoins.sol <<'SOL'
// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

interface LaunchToken {
    function transfer(address, uint256) external returns (bool);
}

interface LaunchFactory {
    function getPool(address, address, uint24) external view returns (address);
    function createPool(address, address, uint24) external returns (address);
}

interface LaunchPool {
    function slot0() external view returns (uint160, int24, uint16, uint16, uint16, uint8, bool);
    function initialize(uint160) external;
    function mint(address, int24, int24, uint128, bytes calldata) external returns (uint256, uint256);
    function swap(address, bool, int256, uint160, bytes calldata) external returns (int256, int256);
    function burn(int24, int24, uint128) external returns (uint256, uint256);
    function collect(address, int24, int24, uint128, uint128) external returns (uint128, uint128);
}

contract FixedCoin {
    string public name;
    string public symbol;
    uint8 public constant decimals = 18;
    uint256 public constant totalSupply = 1_000_000_000e18;
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;
    event Transfer(address indexed from, address indexed to, uint256 amount);
    event Approval(address indexed owner, address indexed spender, uint256 amount);

    constructor(string memory coinName, string memory coinSymbol) {
        name = coinName;
        symbol = coinSymbol;
        balanceOf[msg.sender] = totalSupply;
        emit Transfer(address(0), msg.sender, totalSupply);
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
        if (allowance[from][msg.sender] != type(uint256).max) allowance[from][msg.sender] -= amount;
        move(from, to, amount);
        return true;
    }

    function move(address from, address to, uint256 amount) private {
        require(to != address(0), "zero recipient");
        balanceOf[from] -= amount;
        balanceOf[to] += amount;
        emit Transfer(from, to, amount);
    }
}

contract CreatorCoins {
    address private constant WETH = 0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2;
    LaunchFactory private constant FACTORY = LaunchFactory(0x1F98431c8aD98523631AE4a59f267346ea31F984);
    uint256 private constant Q96 = 2 ** 96;
    uint256 private constant SUPPLY = 1_000_000_000e18;
    // TickMath square-root ratios at -184200, 184200, -887200, and 887200.
    uint256 private constant LOWER = 7929163711037019540271357;
    uint256 private constant UPPER = 791647387308859959733601586197955;
    uint256 private constant MINIMUM = 4310618292;
    uint256 private constant MAXIMUM = 1456195216270955103206513029158776779468408838535;

    struct Position {
        address creator;
        address recipient;
        LaunchPool pool;
        int24 lower;
        int24 upper;
    }

    address private immutable treasury;
    mapping(address => Position) private positions;
    address private callbackPool;

    constructor(address platformRecipient) {
        require(platformRecipient != address(0), "zero platform recipient");
        treasury = platformRecipient;
    }

    function create(string calldata name, string calldata symbol) external returns (address coin) {
        coin = address(new FixedCoin(name, symbol));
        bool coinFirst = coin < WETH;
        uint160 opening = uint160(coinFirst ? Q96 / 10000 : Q96 * 10000);
        address poolAddress = FACTORY.getPool(coin, WETH, 10000);
        if (poolAddress == address(0)) poolAddress = FACTORY.createPool(coin, WETH, 10000);
        LaunchPool pool = LaunchPool(poolAddress);
        (uint160 current,,,,,,) = pool.slot0();
        callbackPool = poolAddress;
        if (current == 0) {
            pool.initialize(opening);
        } else if (current != opening) {
            // An empty pool moves to either price without any input tokens.
            pool.swap(address(this), current > opening, type(int256).max, opening, "");
        }
        int24 lower = coinFirst ? int24(-184200) : int24(-887200);
        int24 upper = coinFirst ? int24(887200) : int24(184200);
        uint128 liquidity = uint128(coinFirst
            ? SUPPLY * LOWER / Q96 * MAXIMUM / (MAXIMUM - LOWER)
            : SUPPLY * Q96 / (UPPER - MINIMUM));
        pool.mint(address(this), lower, upper, liquidity, abi.encode(coin));
        callbackPool = address(0);
        // Mint rounding cannot leave part of the supply with the platform.
        FixedCoin(coin).transfer(poolAddress, FixedCoin(coin).balanceOf(address(this)));
        positions[coin] = Position(msg.sender, msg.sender, pool, lower, upper);
    }

    function collect(address coin) external {
        Position storage position = positions[coin];
        require(address(position.pool) != address(0), "unknown coin");
        // A zero burn updates fees without changing the position's liquidity.
        position.pool.burn(position.lower, position.upper, 0);
        (uint128 amount0, uint128 amount1) = position.pool.collect(
            address(this), position.lower, position.upper, type(uint128).max, type(uint128).max
        );
        (uint256 coinFees, uint256 wethFees) = coin < WETH ? (amount0, amount1) : (amount1, amount0);
        pay(coin, position.recipient, coinFees);
        pay(WETH, position.recipient, wethFees);
    }

    function setPayoutRecipient(address coin, address recipient) external {
        Position storage position = positions[coin];
        require(msg.sender == position.creator, "only creator");
        require(recipient != address(0), "zero recipient");
        position.recipient = recipient;
    }

    function uniswapV3MintCallback(uint256 amount0, uint256 amount1, bytes calldata data) external {
        require(msg.sender == callbackPool, "unexpected mint callback");
        address coin = abi.decode(data, (address));
        uint256 coinOwed = coin < WETH ? amount0 : amount1;
        require((coin < WETH ? amount1 : amount0) == 0, "launch requires WETH");
        require(LaunchToken(coin).transfer(msg.sender, coinOwed), "mint payment failed");
    }

    function uniswapV3SwapCallback(int256 amount0, int256 amount1, bytes calldata) external view {
        require(msg.sender == callbackPool, "unexpected swap callback");
        require(amount0 <= 0 && amount1 <= 0, "pool has blocking liquidity");
    }

    function pay(address token, address recipient, uint256 amount) private {
        if (amount == 0) return;
        uint256 creatorAmount = amount * 70 / 100;
        require(LaunchToken(token).transfer(recipient, creatorAmount), "creator payment failed");
        require(LaunchToken(token).transfer(treasury, amount - creatorAmount), "platform payment failed");
    }
}
SOL
