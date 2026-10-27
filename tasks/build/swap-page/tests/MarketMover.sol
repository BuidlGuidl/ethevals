// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

interface Token {
    function transfer(address, uint256) external returns (bool);
}
interface V3Pool {
    function token0() external view returns (address);
    function token1() external view returns (address);
    function swap(address, bool, int256, uint160, bytes calldata) external returns (int256, int256);
}
struct PoolKey {
    address currency0;
    address currency1;
    uint24 fee;
    int24 tickSpacing;
    address hooks;
}
struct SwapParams {
    bool zeroForOne;
    int256 amountSpecified;
    uint160 sqrtPriceLimitX96;
}
interface Manager {
    function unlock(bytes calldata) external returns (bytes memory);
    function swap(PoolKey calldata, SwapParams calldata, bytes calldata) external returns (int256);
    function sync(address) external;
    function settle() external payable returns (uint256);
    function take(address, address, uint256) external;
}

contract MarketMover {
    address public immutable owner = msg.sender;
    Manager constant manager = Manager(0x000000000004444c5dc75cB358380D2e3dE08A90);
    address private activePool;
    event Moved(int256 amount0, int256 amount1);

    receive() external payable {}

    function pay(address token, address to, uint256 amount) private {
        (bool ok, bytes memory result) = token.call(abi.encodeWithSelector(Token.transfer.selector, to, amount));
        require(ok && (result.length == 0 || abi.decode(result, (bool))), "Token payment failed");
    }

    function moveV3(address pool, bool zeroForOne, uint160 target) external {
        require(msg.sender == owner, "Owner required");
        activePool = pool;
        (int256 a, int256 b) = V3Pool(pool).swap(address(this), zeroForOne, type(int128).max, target, "");
        activePool = address(0);
        emit Moved(a, b);
    }

    function uniswapV3SwapCallback(int256 amount0, int256 amount1, bytes calldata) external {
        require(msg.sender == activePool, "Active pool required");
        if (amount0 > 0) pay(V3Pool(msg.sender).token0(), msg.sender, uint256(amount0));
        if (amount1 > 0) pay(V3Pool(msg.sender).token1(), msg.sender, uint256(amount1));
    }

    function moveV4(PoolKey calldata key, bool zeroForOne, uint160 target) external {
        require(msg.sender == owner, "Owner required");
        manager.unlock(abi.encode(key, zeroForOne, target));
    }

    function settleCurrency(address currency, int128 delta) private {
        if (delta < 0) {
            uint256 amount = uint256(-int256(delta));
            if (currency == address(0)) {
                manager.settle{value: amount}();
            } else {
                manager.sync(currency);
                pay(currency, address(manager), amount);
                manager.settle();
            }
        } else if (delta > 0) {
            manager.take(currency, address(this), uint256(uint128(delta)));
        }
    }

    function unlockCallback(bytes calldata data) external returns (bytes memory) {
        require(msg.sender == address(manager), "Pool manager required");
        (PoolKey memory key, bool zeroForOne, uint160 target) = abi.decode(data, (PoolKey, bool, uint160));
        int256 packed = manager.swap(key, SwapParams(zeroForOne, -type(int128).max, target), "");
        int128 a = int128(packed >> 128);
        int128 b = int128(packed);
        settleCurrency(key.currency0, a);
        settleCurrency(key.currency1, b);
        emit Moved(-int256(a), -int256(b));
        return "";
    }
}
