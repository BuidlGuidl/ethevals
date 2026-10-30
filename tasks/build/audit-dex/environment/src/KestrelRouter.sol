// SPDX-License-Identifier: BUSL-1.1
pragma solidity 0.8.30;

import {IERC20} from "./interfaces/IERC20.sol";
import {IKestrelVault} from "./interfaces/IKestrelVault.sol";
import {KestrelMath} from "./libraries/KestrelMath.sol";
import {SafeTransfer} from "./libraries/SafeTransfer.sol";

/// @title KestrelRouter
/// @notice User entry point for Kestrel. Moves the caller's tokens into the vault and calls it in the
///         same transaction, with deadline and slippage checks.
/// @dev The router holds no tokens between calls.
contract KestrelRouter {
    using SafeTransfer for IERC20;

    IKestrelVault public immutable vault;

    error Expired();
    error InvalidPath();
    error InsufficientAAmount();
    error InsufficientBAmount();
    error InsufficientOutputAmount();

    modifier ensure(uint256 deadline) {
        if (block.timestamp > deadline) revert Expired();
        _;
    }

    constructor(IKestrelVault vault_) {
        vault = vault_;
    }

    // ---------------------------------------------------------------------
    // Liquidity
    // ---------------------------------------------------------------------

    /// @notice Adds liquidity at the pool's current ratio, creating the pool if it does not exist.
    /// @return amountA Token A taken from the caller.
    /// @return amountB Token B taken from the caller.
    /// @return shares Pool shares minted to `to`.
    function addLiquidity(
        address tokenA,
        address tokenB,
        uint16 feeBps,
        uint256 amountADesired,
        uint256 amountBDesired,
        uint256 amountAMin,
        uint256 amountBMin,
        address to,
        uint256 deadline
    ) external ensure(deadline) returns (uint256 amountA, uint256 amountB, uint256 shares) {
        bytes32 poolId;
        (poolId, amountA, amountB) =
            _deliverLiquidity(tokenA, tokenB, feeBps, amountADesired, amountBDesired, amountAMin, amountBMin);
        shares = vault.addLiquidity(poolId, to);
    }

    /// @notice Removes liquidity. The caller must have approved this router as a vault operator.
    function removeLiquidity(
        address tokenA,
        address tokenB,
        uint16 feeBps,
        uint256 shares,
        uint256 amountAMin,
        uint256 amountBMin,
        address to,
        uint256 deadline
    ) external ensure(deadline) returns (uint256 amountA, uint256 amountB) {
        bytes32 poolId = _poolId(tokenA, tokenB, feeBps);
        (uint256 amount0, uint256 amount1) = vault.removeLiquidity(poolId, msg.sender, shares, to);
        (amountA, amountB) = tokenA < tokenB ? (amount0, amount1) : (amount1, amount0);
        if (amountA < amountAMin) revert InsufficientAAmount();
        if (amountB < amountBMin) revert InsufficientBAmount();
    }

    // ---------------------------------------------------------------------
    // Swaps
    // ---------------------------------------------------------------------

    /// @notice Swaps an exact input along `path`, one pool per hop.
    /// @param path Tokens of the route, from input to output.
    /// @param fees Fee tier of each hop; `fees.length` must be `path.length - 1`.
    function swapExactTokensForTokens(
        uint256 amountIn,
        uint256 amountOutMin,
        address[] calldata path,
        uint16[] calldata fees,
        address to,
        uint256 deadline
    ) external ensure(deadline) returns (uint256 amountOut) {
        uint256 hops = _checkPath(path, fees);

        IERC20(path[0]).safeTransferFrom(msg.sender, address(vault), amountIn);
        for (uint256 i; i < hops; ++i) {
            bytes32 poolId = _poolId(path[i], path[i + 1], fees[i]);
            address recipient = i + 1 < hops ? address(vault) : to;
            amountOut = vault.swap(poolId, path[i], recipient);
        }
        if (amountOut < amountOutMin) revert InsufficientOutputAmount();
    }

    /// @notice Expected output of `swapExactTokensForTokens` at current reserves.
    function quoteExactIn(uint256 amountIn, address[] calldata path, uint16[] calldata fees)
        external
        view
        returns (uint256 amountOut)
    {
        uint256 hops = _checkPath(path, fees);
        amountOut = amountIn;
        for (uint256 i; i < hops; ++i) {
            bytes32 poolId = _poolId(path[i], path[i + 1], fees[i]);
            IKestrelVault.Pool memory pool = vault.getPool(poolId);
            (uint256 reserveIn, uint256 reserveOut) =
                path[i] == pool.token0 ? (pool.reserve0, pool.reserve1) : (pool.reserve1, pool.reserve0);
            amountOut = KestrelMath.getAmountOut(amountOut, reserveIn, reserveOut, vault.swapFee(poolId));
        }
    }

    // ---------------------------------------------------------------------
    // Internal
    // ---------------------------------------------------------------------

    function _poolId(address tokenA, address tokenB, uint16 feeBps) internal view returns (bytes32) {
        (address token0, address token1) = tokenA < tokenB ? (tokenA, tokenB) : (tokenB, tokenA);
        return vault.computePoolId(token0, token1, feeBps);
    }

    function _checkPath(address[] calldata path, uint16[] calldata fees) internal pure returns (uint256 hops) {
        if (path.length < 2 || fees.length != path.length - 1) revert InvalidPath();
        hops = fees.length;
    }

    /// @dev Creates the pool if needed and moves the ratio-matched amounts from the caller to the vault.
    function _deliverLiquidity(
        address tokenA,
        address tokenB,
        uint16 feeBps,
        uint256 amountADesired,
        uint256 amountBDesired,
        uint256 amountAMin,
        uint256 amountBMin
    ) internal returns (bytes32 poolId, uint256 amountA, uint256 amountB) {
        poolId = _poolId(tokenA, tokenB, feeBps);
        if (!vault.poolExists(poolId)) vault.createPool(tokenA, tokenB, feeBps);

        (amountA, amountB) = _optimalAmounts(poolId, tokenA, amountADesired, amountBDesired, amountAMin, amountBMin);

        IERC20(tokenA).safeTransferFrom(msg.sender, address(vault), amountA);
        IERC20(tokenB).safeTransferFrom(msg.sender, address(vault), amountB);
    }

    /// @dev Uniswap V2 style: keep one desired amount and scale the other to the pool's ratio.
    function _optimalAmounts(
        bytes32 poolId,
        address tokenA,
        uint256 amountADesired,
        uint256 amountBDesired,
        uint256 amountAMin,
        uint256 amountBMin
    ) internal view returns (uint256 amountA, uint256 amountB) {
        IKestrelVault.Pool memory pool = vault.getPool(poolId);
        (uint256 reserveA, uint256 reserveB) =
            tokenA == pool.token0 ? (pool.reserve0, pool.reserve1) : (pool.reserve1, pool.reserve0);
        if (reserveA == 0 && reserveB == 0) return (amountADesired, amountBDesired);

        uint256 amountBOptimal = KestrelMath.quote(amountADesired, reserveA, reserveB);
        if (amountBOptimal <= amountBDesired) {
            if (amountBOptimal < amountBMin) revert InsufficientBAmount();
            return (amountADesired, amountBOptimal);
        }
        uint256 amountAOptimal = KestrelMath.quote(amountBDesired, reserveB, reserveA);
        if (amountAOptimal < amountAMin) revert InsufficientAAmount();
        return (amountAOptimal, amountBDesired);
    }
}
