// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

interface IKestrelVault {
    struct Pool {
        address token0;
        address token1;
        uint16 feeBps;
        uint256 reserve0;
        uint256 reserve1;
        uint256 totalShares;
    }

    event PoolCreated(bytes32 indexed poolId, address indexed token0, address indexed token1, uint16 feeBps);
    event LiquidityAdded(bytes32 indexed poolId, address indexed to, uint256 amount0, uint256 amount1, uint256 shares);
    event LiquidityRemoved(
        bytes32 indexed poolId, address indexed owner, address to, uint256 amount0, uint256 amount1, uint256 shares
    );
    event Swap(
        bytes32 indexed poolId, address indexed tokenIn, uint256 amountIn, uint256 amountOut, uint256 protocolFee, address to
    );
    event OperatorSet(address indexed owner, address indexed operator, bool approved);
    event ProtocolFeesCollected(address indexed token, address indexed recipient, uint256 amount);
    event Skimmed(address indexed token, address indexed to, uint256 amount);
    event FeeTierSet(uint16 feeBps, bool enabled);
    event ProtocolShareSet(uint16 protocolShareBps);
    event FeeRecipientSet(address feeRecipient);
    event OwnershipTransferStarted(address indexed previousOwner, address indexed newOwner);
    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);

    error Unauthorized();
    error Reentrancy();
    error InvalidPool();
    error PoolExists();
    error FeeTierDisabled();
    error InvalidToken();
    error InsufficientShares();
    error InsufficientAmount();
    error InvalidRecipient();
    error ProtocolShareTooHigh();

    function computePoolId(address token0, address token1, uint16 feeBps) external pure returns (bytes32);
    function getPool(bytes32 poolId) external view returns (Pool memory);
    function poolExists(bytes32 poolId) external view returns (bool);
    function sharesOf(bytes32 poolId, address account) external view returns (uint256);
    function isOperator(address owner, address operator) external view returns (bool);

    function createPool(address tokenA, address tokenB, uint16 feeBps) external returns (bytes32 poolId);
    function addLiquidity(bytes32 poolId, address to) external returns (uint256 shares);
    function removeLiquidity(bytes32 poolId, address owner, uint256 shares, address to)
        external
        returns (uint256 amount0, uint256 amount1);
    function swap(bytes32 poolId, address tokenIn, address to) external returns (uint256 amountOut);
    function setOperator(address operator, bool approved) external;
    function skim(address token, address to) external returns (uint256 amount);
    function collectProtocolFees(address[] calldata tokens) external;
}
