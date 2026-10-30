// SPDX-License-Identifier: BUSL-1.1
pragma solidity 0.8.30;

import {IERC20} from "./interfaces/IERC20.sol";
import {IKestrelVault} from "./interfaces/IKestrelVault.sol";
import {SafeTransfer} from "./libraries/SafeTransfer.sol";

/// @title KestrelFarm
/// @notice Liquidity providers stake their Kestrel pool shares here to earn rewards. Each pool has a
///         few reward tokens, and each reward streams to the pool's stakers over seven days.
/// @dev The farm is the vault's protocol fee recipient. After the keeper collects fees, anyone can
///      call `distributeFees` to stream them to the stakers of the pool the owner picked for that token.
///      Stakers approve the farm as a vault operator so it can move their shares.
contract KestrelFarm {
    using SafeTransfer for IERC20;

    uint256 public constant DURATION = 7 days;
    uint256 public constant MAX_REWARDS_PER_POOL = 4;
    uint256 internal constant PRECISION = 1e18;

    struct Reward {
        uint256 rate;
        uint256 periodFinish;
        uint256 lastUpdate;
        uint256 perShareStored;
    }

    IKestrelVault public immutable vault;
    address public owner;

    mapping(bytes32 poolId => uint256) public totalStaked;
    mapping(bytes32 poolId => mapping(address account => uint256)) public staked;
    mapping(bytes32 poolId => address[]) internal _rewardTokens;
    mapping(address token => bytes32[]) internal _poolsOf;
    mapping(bytes32 poolId => mapping(address token => Reward)) public rewards;
    mapping(bytes32 poolId => mapping(address token => mapping(address account => uint256))) public perSharePaid;
    mapping(bytes32 poolId => mapping(address token => mapping(address account => uint256))) public earnedStored;
    /// @notice Rewards stakers have earned and not yet claimed, per token, across all pools.
    mapping(address token => uint256) public unclaimed;
    /// @notice Pool whose stakers receive the protocol fees the farm collects in each token.
    mapping(address token => bytes32 poolId) public feeTarget;

    event RewardAdded(bytes32 indexed poolId, address indexed token);
    event RewardNotified(bytes32 indexed poolId, address indexed token, uint256 amount, uint256 rate);
    event FeeTargetSet(address indexed token, bytes32 indexed poolId);
    event Staked(bytes32 indexed poolId, address indexed account, uint256 shares);
    event Withdrawn(bytes32 indexed poolId, address indexed account, address to, uint256 shares);
    event Claimed(bytes32 indexed poolId, address indexed account, address indexed token, uint256 amount);
    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);

    error Unauthorized();
    error UnknownReward();
    error RewardExists();
    error TooManyRewards();
    error NoFeeTarget();
    error ZeroAmount();
    error RewardTooSmall();

    modifier onlyOwner() {
        if (msg.sender != owner) revert Unauthorized();
        _;
    }

    constructor(IKestrelVault vault_, address owner_) {
        vault = vault_;
        owner = owner_;
        emit OwnershipTransferred(address(0), owner_);
    }

    // ---------------------------------------------------------------------
    // Views
    // ---------------------------------------------------------------------

    function rewardTokens(bytes32 poolId) external view returns (address[] memory) {
        return _rewardTokens[poolId];
    }

    function isReward(bytes32 poolId, address token) public view returns (bool) {
        return rewards[poolId][token].lastUpdate != 0;
    }

    /// @notice Reward `account` could claim now from `poolId` in `token`.
    function earned(bytes32 poolId, address token, address account) public view returns (uint256) {
        Reward storage r = rewards[poolId][token];
        uint256 perShare = r.perShareStored;
        uint256 supply = totalStaked[poolId];
        uint256 until = _min(block.timestamp, r.periodFinish);
        if (supply != 0 && until > r.lastUpdate) perShare += r.rate * (until - r.lastUpdate) * PRECISION / supply;
        return earnedStored[poolId][token][account]
            + staked[poolId][account] * (perShare - perSharePaid[poolId][token][account]) / PRECISION;
    }

    // ---------------------------------------------------------------------
    // Stakers
    // ---------------------------------------------------------------------

    /// @notice Stakes `shares` of the caller's pool shares. The caller must have approved this farm as
    ///         a vault operator.
    function stake(bytes32 poolId, uint256 shares) external {
        if (shares == 0) revert ZeroAmount();
        _checkpoint(poolId, msg.sender);
        staked[poolId][msg.sender] += shares;
        totalStaked[poolId] += shares;
        vault.transferShares(poolId, msg.sender, address(this), shares);
        emit Staked(poolId, msg.sender, shares);
    }

    /// @notice Unstakes `shares` and returns them to `to` as vault pool shares.
    function withdraw(bytes32 poolId, uint256 shares, address to) external {
        if (shares == 0) revert ZeroAmount();
        _checkpoint(poolId, msg.sender);
        staked[poolId][msg.sender] -= shares;
        totalStaked[poolId] -= shares;
        vault.transferShares(poolId, address(this), to, shares);
        emit Withdrawn(poolId, msg.sender, to, shares);
    }

    /// @notice Sends the caller every reward they have earned in `poolId`.
    function claim(bytes32 poolId) external {
        _checkpoint(poolId, msg.sender);
        address[] storage tokens = _rewardTokens[poolId];
        for (uint256 i; i < tokens.length; ++i) {
            address token = tokens[i];
            uint256 amount = earnedStored[poolId][token][msg.sender];
            if (amount == 0) continue;
            earnedStored[poolId][token][msg.sender] = 0;
            unclaimed[token] -= amount;
            IERC20(token).safeTransfer(msg.sender, amount);
            emit Claimed(poolId, msg.sender, token, amount);
        }
    }

    // ---------------------------------------------------------------------
    // Funding
    // ---------------------------------------------------------------------

    /// @notice Adds `amount` of `token` to the pool's reward stream. Anyone may fund a reward the owner
    ///         has added, for example a token team paying for liquidity in its pool.
    function fund(bytes32 poolId, address token, uint256 amount) external {
        if (!isReward(poolId, token)) revert UnknownReward();
        if (amount == 0) revert ZeroAmount();
        IERC20(token).safeTransferFrom(msg.sender, address(this), amount);
        _notify(poolId, token, amount);
    }

    /// @notice Streams the protocol fees the farm has received in `token` to the stakers of the pool
    ///         the owner picked for it. Anyone may call it; the keeper does after each collection.
    function distributeFees(address token) external {
        bytes32 poolId = feeTarget[token];
        if (poolId == bytes32(0)) revert NoFeeTarget();
        // Bring every stream of this token up to date, so `unclaimed` holds all rewards earned so far.
        bytes32[] storage pools = _poolsOf[token];
        for (uint256 i; i < pools.length; ++i) {
            _accrue(pools[i], token);
        }
        uint256 amount = IERC20(token).balanceOf(address(this)) - unclaimed[token];
        _notify(poolId, token, amount);
    }

    // ---------------------------------------------------------------------
    // Admin
    // ---------------------------------------------------------------------

    function addReward(bytes32 poolId, address token) external onlyOwner {
        if (!vault.poolExists(poolId)) revert UnknownReward();
        if (isReward(poolId, token)) revert RewardExists();
        if (_rewardTokens[poolId].length == MAX_REWARDS_PER_POOL) revert TooManyRewards();
        _rewardTokens[poolId].push(token);
        _poolsOf[token].push(poolId);
        rewards[poolId][token].lastUpdate = block.timestamp;
        emit RewardAdded(poolId, token);
    }

    function setFeeTarget(address token, bytes32 poolId) external onlyOwner {
        if (!isReward(poolId, token)) revert UnknownReward();
        feeTarget[token] = poolId;
        emit FeeTargetSet(token, poolId);
    }

    function transferOwnership(address newOwner) external onlyOwner {
        emit OwnershipTransferred(owner, newOwner);
        owner = newOwner;
    }

    // ---------------------------------------------------------------------
    // Internal
    // ---------------------------------------------------------------------

    /// @dev Starts a new seven-day stream of `amount`, rolling in what is left of the current one.
    function _notify(bytes32 poolId, address token, uint256 amount) internal {
        Reward storage r = rewards[poolId][token];
        _accrue(poolId, token);
        if (block.timestamp < r.periodFinish) amount += r.rate * (r.periodFinish - block.timestamp);
        uint256 rate = amount / DURATION;
        if (rate == 0) revert RewardTooSmall();
        r.rate = rate;
        r.lastUpdate = block.timestamp;
        r.periodFinish = block.timestamp + DURATION;
        emit RewardNotified(poolId, token, amount, rate);
    }

    /// @dev Moves a stream forward to now and records what its stakers have earned since the last update.
    function _accrue(bytes32 poolId, address token) internal {
        Reward storage r = rewards[poolId][token];
        uint256 until = _min(block.timestamp, r.periodFinish);
        if (until <= r.lastUpdate) return;
        uint256 supply = totalStaked[poolId];
        if (supply != 0) {
            uint256 amount = r.rate * (until - r.lastUpdate);
            r.perShareStored += amount * PRECISION / supply;
            unclaimed[token] += amount;
        }
        r.lastUpdate = until;
    }

    /// @dev Brings every reward of `poolId` up to date and books what `account` has earned.
    function _checkpoint(bytes32 poolId, address account) internal {
        address[] storage tokens = _rewardTokens[poolId];
        for (uint256 i; i < tokens.length; ++i) {
            address token = tokens[i];
            _accrue(poolId, token);
            uint256 perShare = rewards[poolId][token].perShareStored;
            earnedStored[poolId][token][account] +=
                staked[poolId][account] * (perShare - perSharePaid[poolId][token][account]) / PRECISION;
            perSharePaid[poolId][token][account] = perShare;
        }
    }

    function _min(uint256 a, uint256 b) internal pure returns (uint256) {
        return a < b ? a : b;
    }
}
