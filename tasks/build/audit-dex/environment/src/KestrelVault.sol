// SPDX-License-Identifier: BUSL-1.1
pragma solidity 0.8.30;

import {IERC20} from "./interfaces/IERC20.sol";
import {IKestrelFeeModule} from "./interfaces/IKestrelFeeModule.sol";
import {IKestrelVault} from "./interfaces/IKestrelVault.sol";
import {KestrelMath} from "./libraries/KestrelMath.sol";
import {SafeTransfer} from "./libraries/SafeTransfer.sol";

/// @title KestrelVault
/// @notice Singleton vault that holds the tokens of every Kestrel constant-product pool.
/// @dev Callers deliver input tokens to the vault and then call `addLiquidity` or `swap` in the same
///      transaction. The vault credits the caller with the tokens it received since its last accounting.
///      `KestrelRouter` is the supported way to do this.
contract KestrelVault is IKestrelVault {
    using SafeTransfer for IERC20;

    /// @notice Shares locked forever on a pool's first deposit.
    uint256 public constant MINIMUM_LIQUIDITY = 1000;
    uint256 public constant BPS = 10_000;
    /// @notice Highest share of the swap fee the protocol may take.
    uint16 public constant MAX_PROTOCOL_SHARE_BPS = 2500;
    /// @notice Swap fees, in basis points, must stay below this.
    uint16 public constant MAX_FEE_BPS = 1000;

    address public owner;
    address public pendingOwner;
    address public feeRecipient;
    /// @notice Share of each swap fee, in basis points of the fee, kept for the protocol.
    uint16 public protocolShareBps;

    mapping(uint16 feeBps => bool) public feeTierEnabled;
    /// @notice Optional module that sets the swap fee of every pool at a tier.
    mapping(uint16 feeBps => address) public feeModule;
    mapping(bytes32 poolId => Pool) internal _pools;
    mapping(bytes32 poolId => mapping(address account => uint256)) public sharesOf;
    mapping(address owner => mapping(address operator => bool)) public isOperator;
    /// @notice Tokens the vault has accounted for: pool reserves plus uncollected protocol fees.
    mapping(address token => uint256) public trackedBalance;
    /// @notice Protocol fees accrued per token and not yet collected.
    mapping(address token => uint256) public protocolFees;

    uint256 private _lock = 1;

    modifier nonReentrant() {
        if (_lock != 1) revert Reentrancy();
        _lock = 2;
        _;
        _lock = 1;
    }

    modifier onlyOwner() {
        if (msg.sender != owner) revert Unauthorized();
        _;
    }

    constructor(address owner_, address feeRecipient_, uint16 protocolShareBps_) {
        if (owner_ == address(0) || feeRecipient_ == address(0)) revert InvalidRecipient();
        if (protocolShareBps_ > MAX_PROTOCOL_SHARE_BPS) revert ProtocolShareTooHigh();
        owner = owner_;
        feeRecipient = feeRecipient_;
        protocolShareBps = protocolShareBps_;
        feeTierEnabled[5] = true;
        feeTierEnabled[30] = true;
        feeTierEnabled[100] = true;
        emit OwnershipTransferred(address(0), owner_);
    }

    // ---------------------------------------------------------------------
    // Views
    // ---------------------------------------------------------------------

    /// @inheritdoc IKestrelVault
    function computePoolId(address token0, address token1, uint16 feeBps) public pure returns (bytes32) {
        return keccak256(abi.encode(token0, token1, feeBps));
    }

    /// @inheritdoc IKestrelVault
    function getPool(bytes32 poolId) external view returns (Pool memory) {
        return _pools[poolId];
    }

    /// @inheritdoc IKestrelVault
    function poolExists(bytes32 poolId) public view returns (bool) {
        return _pools[poolId].token0 != address(0);
    }

    /// @inheritdoc IKestrelVault
    function swapFee(bytes32 poolId) public view returns (uint16) {
        Pool storage pool = _pools[poolId];
        uint16 tierFee = pool.feeBps;
        address module = feeModule[tierFee];
        if (module == address(0)) return tierFee;
        // A module may raise a pool's fee above its tier. An answer outside the fee range the vault
        // accepts falls back to the tier fee, so a faulty module cannot block or drain swaps.
        uint256 fee = IKestrelFeeModule(module).swapFee(poolId);
        if (fee < tierFee || fee >= MAX_FEE_BPS) return tierFee;
        return uint16(fee);
    }

    // ---------------------------------------------------------------------
    // Pools
    // ---------------------------------------------------------------------

    /// @notice Creates an empty pool for a token pair at an enabled fee tier. Anyone may call it.
    function createPool(address tokenA, address tokenB, uint16 feeBps) external returns (bytes32 poolId) {
        if (tokenA == tokenB || tokenA == address(0) || tokenB == address(0)) revert InvalidToken();
        if (!feeTierEnabled[feeBps]) revert FeeTierDisabled();
        (address token0, address token1) = tokenA < tokenB ? (tokenA, tokenB) : (tokenB, tokenA);
        poolId = computePoolId(token0, token1, feeBps);
        if (poolExists(poolId)) revert PoolExists();
        _pools[poolId] = Pool({
            token0: token0,
            token1: token1,
            feeBps: feeBps,
            createdAt: uint40(block.timestamp),
            reserve0: 0,
            reserve1: 0,
            totalShares: 0
        });
        emit PoolCreated(poolId, token0, token1, feeBps);
    }

    /// @notice Credits the tokens delivered since the last accounting to a pool and mints shares to `to`.
    /// @dev Deposits beyond the pool's current ratio stay in the pool and accrue to all shareholders.
    function addLiquidity(bytes32 poolId, address to) external nonReentrant returns (uint256 shares) {
        Pool storage pool = _pools[poolId];
        if (pool.token0 == address(0)) revert InvalidPool();
        if (to == address(0)) revert InvalidRecipient();

        uint256 amount0 = _settle(pool.token0);
        uint256 amount1 = _settle(pool.token1);

        uint256 totalShares = pool.totalShares;
        if (totalShares == 0) {
            shares = KestrelMath.sqrt(amount0 * amount1) - MINIMUM_LIQUIDITY;
            sharesOf[poolId][address(0)] = MINIMUM_LIQUIDITY;
            totalShares = MINIMUM_LIQUIDITY;
        } else {
            shares = KestrelMath.min(amount0 * totalShares / pool.reserve0, amount1 * totalShares / pool.reserve1);
        }
        if (shares == 0) revert InsufficientShares();

        pool.reserve0 += amount0;
        pool.reserve1 += amount1;
        pool.totalShares = totalShares + shares;
        sharesOf[poolId][to] += shares;

        emit LiquidityAdded(poolId, to, amount0, amount1, shares);
    }

    /// @notice Burns `shares` held by `owner_` and sends the pro-rata reserves to `to`.
    /// @dev The caller must be `owner_` or an operator approved by `owner_`.
    function removeLiquidity(bytes32 poolId, address owner_, uint256 shares, address to)
        external
        nonReentrant
        returns (uint256 amount0, uint256 amount1)
    {
        if (msg.sender != owner_ && !isOperator[owner_][msg.sender]) revert Unauthorized();
        Pool storage pool = _pools[poolId];
        if (pool.token0 == address(0)) revert InvalidPool();
        if (to == address(0)) revert InvalidRecipient();
        if (shares == 0 || sharesOf[poolId][owner_] < shares) revert InsufficientShares();

        uint256 totalShares = pool.totalShares;
        amount0 = shares * pool.reserve0 / totalShares;
        amount1 = shares * pool.reserve1 / totalShares;
        if (amount0 == 0 && amount1 == 0) revert InsufficientAmount();

        sharesOf[poolId][owner_] -= shares;
        pool.totalShares = totalShares - shares;
        pool.reserve0 -= amount0;
        pool.reserve1 -= amount1;

        _send(pool.token0, to, amount0);
        _send(pool.token1, to, amount1);

        emit LiquidityRemoved(poolId, owner_, to, amount0, amount1, shares);
    }

    /// @notice Swaps the `tokenIn` delivered since the last accounting for the pool's other token.
    /// @dev The output may be sent to this vault to chain into the next pool of a route.
    function swap(bytes32 poolId, address tokenIn, address to) external nonReentrant returns (uint256 amountOut) {
        Pool storage pool = _pools[poolId];
        if (pool.token0 == address(0)) revert InvalidPool();
        if (to == address(0)) revert InvalidRecipient();
        bool zeroForOne = tokenIn == pool.token0;
        if (!zeroForOne && tokenIn != pool.token1) revert InvalidToken();

        uint256 amountIn = _settle(tokenIn);
        uint256 feeBps = swapFee(poolId);
        (uint256 reserveIn, uint256 reserveOut) = zeroForOne ? (pool.reserve0, pool.reserve1) : (pool.reserve1, pool.reserve0);
        amountOut = KestrelMath.getAmountOut(amountIn, reserveIn, reserveOut, feeBps);
        if (amountOut == 0) revert InsufficientAmount();

        uint256 protocolFee = amountIn * feeBps / BPS * protocolShareBps / BPS;
        protocolFees[tokenIn] += protocolFee;

        address tokenOut;
        if (zeroForOne) {
            pool.reserve0 = reserveIn + amountIn - protocolFee;
            pool.reserve1 = reserveOut - amountOut;
            tokenOut = pool.token1;
        } else {
            pool.reserve1 = reserveIn + amountIn - protocolFee;
            pool.reserve0 = reserveOut - amountOut;
            tokenOut = pool.token0;
        }

        _send(tokenOut, to, amountOut);

        emit Swap(poolId, tokenIn, amountIn, amountOut, protocolFee, to);
    }

    // ---------------------------------------------------------------------
    // Accounts
    // ---------------------------------------------------------------------

    /// @notice Lets `operator` remove liquidity on the caller's behalf, as the router does.
    function setOperator(address operator, bool approved) external {
        isOperator[msg.sender][operator] = approved;
        emit OperatorSet(msg.sender, operator, approved);
    }

    /// @notice Moves pool shares from `from` to `to`, as the farm does when liquidity providers stake.
    /// @dev The caller must be `from` or an operator approved by `from`.
    function transferShares(bytes32 poolId, address from, address to, uint256 shares) external {
        if (msg.sender != from && !isOperator[from][msg.sender]) revert Unauthorized();
        if (to == address(0)) revert InvalidRecipient();
        if (sharesOf[poolId][from] < shares) revert InsufficientShares();
        sharesOf[poolId][from] -= shares;
        sharesOf[poolId][to] += shares;
        emit SharesTransferred(poolId, from, to, shares);
    }

    /// @notice Sends tokens the vault holds beyond its accounting, such as direct transfers, to `to`.
    function skim(address token, address to) external nonReentrant returns (uint256 amount) {
        if (to == address(0)) revert InvalidRecipient();
        amount = IERC20(token).balanceOf(address(this)) - trackedBalance[token];
        if (amount != 0) IERC20(token).safeTransfer(to, amount);
        emit Skimmed(token, to, amount);
    }

    /// @notice Sends accrued protocol fees for each token to the fee recipient. Anyone may call it.
    function collectProtocolFees(address[] calldata tokens) external nonReentrant {
        address recipient = feeRecipient;
        for (uint256 i; i < tokens.length; ++i) {
            address token = tokens[i];
            uint256 amount = protocolFees[token];
            if (amount == 0) continue;
            protocolFees[token] = 0;
            _send(token, recipient, amount);
            emit ProtocolFeesCollected(token, recipient, amount);
        }
    }

    // ---------------------------------------------------------------------
    // Admin
    // ---------------------------------------------------------------------

    function setFeeTier(uint16 feeBps, bool enabled) external onlyOwner {
        if (feeBps == 0 || feeBps >= MAX_FEE_BPS) revert FeeTierDisabled();
        feeTierEnabled[feeBps] = enabled;
        emit FeeTierSet(feeBps, enabled);
    }

    /// @notice Sets the fee module for a tier, or removes it with the zero address.
    function setFeeModule(uint16 feeBps, address module) external onlyOwner {
        feeModule[feeBps] = module;
        emit FeeModuleSet(feeBps, module);
    }

    function setProtocolShare(uint16 protocolShareBps_) external onlyOwner {
        if (protocolShareBps_ > MAX_PROTOCOL_SHARE_BPS) revert ProtocolShareTooHigh();
        protocolShareBps = protocolShareBps_;
        emit ProtocolShareSet(protocolShareBps_);
    }

    function setFeeRecipient(address feeRecipient_) external onlyOwner {
        if (feeRecipient_ == address(0)) revert InvalidRecipient();
        feeRecipient = feeRecipient_;
        emit FeeRecipientSet(feeRecipient_);
    }

    function transferOwnership(address newOwner) external onlyOwner {
        pendingOwner = newOwner;
        emit OwnershipTransferStarted(owner, newOwner);
    }

    function acceptOwnership() external {
        if (msg.sender != pendingOwner) revert Unauthorized();
        emit OwnershipTransferred(owner, msg.sender);
        owner = msg.sender;
        pendingOwner = address(0);
    }

    // ---------------------------------------------------------------------
    // Internal
    // ---------------------------------------------------------------------

    /// @dev Returns the tokens received since the last accounting and records the new balance.
    function _settle(address token) internal returns (uint256 received) {
        uint256 balance = IERC20(token).balanceOf(address(this));
        received = balance - trackedBalance[token];
        trackedBalance[token] = balance;
    }

    /// @dev Sends tokens out of the vault and removes them from its accounting.
    function _send(address token, address to, uint256 amount) internal {
        if (amount == 0) return;
        trackedBalance[token] -= amount;
        IERC20(token).safeTransfer(to, amount);
    }
}
