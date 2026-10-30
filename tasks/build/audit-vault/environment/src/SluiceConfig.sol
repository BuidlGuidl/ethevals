// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {IStrategy} from "./interfaces/IStrategy.sol";

/// @title SluiceConfig
/// @notice Roles and timelocked settings for a SluiceVault.
/// @dev Changes that can hurt depositors (raising a fee, adding a strategy, raising a cap, shortening the
///      timelock, replacing the guardian) are submitted first and take effect only after `timelock`.
///      Changes that only reduce risk apply at once. The guardian can revoke any pending change.
abstract contract SluiceConfig {
    uint256 public constant MAX_BPS = 10_000;
    uint256 public constant MAX_PERFORMANCE_FEE = 3_000;
    uint256 public constant MAX_MANAGEMENT_FEE = 200;
    uint256 public constant MIN_TIMELOCK = 1 days;
    uint256 public constant MAX_TIMELOCK = 14 days;

    /// @notice A submitted change and the time it can be accepted.
    struct Pending {
        uint256 value;
        uint64 validAt;
    }

    address public owner;
    address public pendingOwner;
    address public curator;
    address public guardian;
    address public treasury;
    /// @notice The swap router incentive rewards are sold through.
    address public rewardSwapper;
    mapping(address => bool) public isAllocator;

    /// @notice The treasury's share of strategy profit, in basis points.
    uint256 public performanceFee;
    /// @notice The treasury's yearly charge on total assets, in basis points.
    uint256 public managementFee;
    /// @notice Seconds a submitted change waits before it can be accepted.
    uint256 public timelock;
    /// @notice The most the vault will hold, in assets.
    uint256 public depositLimit;
    /// @notice When set, deposits and moves into strategies are stopped. Withdrawals stay open.
    bool public paused;

    Pending public pendingPerformanceFee;
    Pending public pendingManagementFee;
    Pending public pendingTimelock;
    Pending public pendingGuardian;
    /// @notice Strategies submitted for adding, with the cap they will start at.
    mapping(IStrategy => Pending) public pendingStrategy;
    /// @notice Cap raises waiting on the timelock.
    mapping(IStrategy => Pending) public pendingCap;

    event OwnershipTransferStarted(address indexed owner, address indexed pendingOwner);
    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);
    event CuratorSet(address indexed curator);
    event AllocatorSet(address indexed allocator, bool isAllocator);
    event TreasurySet(address indexed treasury);
    event RewardSwapperSet(address indexed swapper);
    event DepositLimitSet(uint256 limit);
    event PausedSet(address indexed caller, bool paused);
    event PerformanceFeeSubmitted(uint256 fee, uint64 validAt);
    event PerformanceFeeSet(uint256 fee);
    event ManagementFeeSubmitted(uint256 fee, uint64 validAt);
    event ManagementFeeSet(uint256 fee);
    event TimelockSubmitted(uint256 timelock, uint64 validAt);
    event TimelockSet(uint256 timelock);
    event GuardianSubmitted(address indexed guardian, uint64 validAt);
    event GuardianSet(address indexed guardian);
    event StrategySubmitted(IStrategy indexed strategy, uint256 cap, uint64 validAt);
    event CapSubmitted(IStrategy indexed strategy, uint256 cap, uint64 validAt);
    event PendingRevoked(address indexed caller, bytes32 indexed what, IStrategy indexed strategy);

    error Unauthorized();
    error FeeTooHigh();
    error TimelockOutOfBounds();
    error NothingPending();
    error TimelockNotElapsed();
    error AlreadySet();
    error AlreadyPending();
    error IsPaused();
    error ZeroTreasury();

    modifier onlyOwner() {
        if (msg.sender != owner) revert Unauthorized();
        _;
    }

    modifier onlyCurator() {
        if (msg.sender != curator && msg.sender != owner) revert Unauthorized();
        _;
    }

    modifier onlyAllocator() {
        if (!isAllocator[msg.sender] && msg.sender != curator && msg.sender != owner) revert Unauthorized();
        _;
    }

    modifier onlyGuardian() {
        if (msg.sender != guardian && msg.sender != owner) revert Unauthorized();
        _;
    }

    modifier whenNotPaused() {
        if (paused) revert IsPaused();
        _;
    }

    /// @param timelock_ May be zero so the team can configure the vault at deployment. Every later
    ///        change through `submitTimelock` must be between MIN_TIMELOCK and MAX_TIMELOCK.
    constructor(
        address owner_,
        address treasury_,
        uint256 timelock_,
        uint256 performanceFee_,
        uint256 managementFee_
    ) {
        if (timelock_ > MAX_TIMELOCK) revert TimelockOutOfBounds();
        if (performanceFee_ > MAX_PERFORMANCE_FEE || managementFee_ > MAX_MANAGEMENT_FEE) revert FeeTooHigh();
        owner = owner_;
        treasury = treasury_;
        timelock = timelock_;
        performanceFee = performanceFee_;
        managementFee = managementFee_;
        depositLimit = type(uint256).max;
    }

    // ---------------------------------------------------------------------
    // Owner: immediate
    // ---------------------------------------------------------------------

    function setCurator(address curator_) external onlyOwner {
        if (curator_ == curator) revert AlreadySet();
        curator = curator_;
        emit CuratorSet(curator_);
    }

    function setIsAllocator(address allocator, bool allowed) external onlyOwner {
        if (isAllocator[allocator] == allowed) revert AlreadySet();
        isAllocator[allocator] = allowed;
        emit AllocatorSet(allocator, allowed);
    }

    function setTreasury(address treasury_) external onlyOwner {
        if (treasury_ == address(0)) revert ZeroTreasury();
        treasury = treasury_;
        emit TreasurySet(treasury_);
    }

    function setRewardSwapper(address swapper) external onlyOwner {
        if (swapper == rewardSwapper) revert AlreadySet();
        rewardSwapper = swapper;
        emit RewardSwapperSet(swapper);
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
    // Owner: timelocked
    // ---------------------------------------------------------------------

    /// @notice A lower fee applies at once; a higher one waits for the timelock.
    function submitPerformanceFee(uint256 fee) external onlyOwner {
        if (fee > MAX_PERFORMANCE_FEE) revert FeeTooHigh();
        if (fee == performanceFee) revert AlreadySet();
        if (fee < performanceFee) {
            _setPerformanceFee(fee);
            return;
        }
        uint64 validAt = _validAt();
        pendingPerformanceFee = Pending(fee, validAt);
        emit PerformanceFeeSubmitted(fee, validAt);
    }

    function acceptPerformanceFee() external {
        _setPerformanceFee(_consume(pendingPerformanceFee));
    }

    /// @notice A lower fee applies at once; a higher one waits for the timelock.
    function submitManagementFee(uint256 fee) external onlyOwner {
        if (fee > MAX_MANAGEMENT_FEE) revert FeeTooHigh();
        if (fee == managementFee) revert AlreadySet();
        if (fee < managementFee) {
            _setManagementFee(fee);
            return;
        }
        uint64 validAt = _validAt();
        pendingManagementFee = Pending(fee, validAt);
        emit ManagementFeeSubmitted(fee, validAt);
    }

    function acceptManagementFee() external {
        _setManagementFee(_consume(pendingManagementFee));
    }

    /// @notice A longer timelock applies at once; a shorter one waits for the current timelock.
    function submitTimelock(uint256 newTimelock) external onlyOwner {
        if (newTimelock < MIN_TIMELOCK || newTimelock > MAX_TIMELOCK) revert TimelockOutOfBounds();
        if (newTimelock == timelock) revert AlreadySet();
        if (newTimelock > timelock) {
            _setTimelock(newTimelock);
            return;
        }
        uint64 validAt = _validAt();
        pendingTimelock = Pending(newTimelock, validAt);
        emit TimelockSubmitted(newTimelock, validAt);
    }

    function acceptTimelock() external {
        _setTimelock(_consume(pendingTimelock));
    }

    /// @notice The first guardian is set at once; replacing or removing one waits for the timelock.
    function submitGuardian(address newGuardian) external onlyOwner {
        if (newGuardian == guardian) revert AlreadySet();
        if (guardian == address(0)) {
            _setGuardian(newGuardian);
            return;
        }
        uint64 validAt = _validAt();
        pendingGuardian = Pending(uint256(uint160(newGuardian)), validAt);
        emit GuardianSubmitted(newGuardian, validAt);
    }

    function acceptGuardian() external {
        _setGuardian(address(uint160(_consume(pendingGuardian))));
    }

    // ---------------------------------------------------------------------
    // Curator
    // ---------------------------------------------------------------------

    /// @notice Submits a strategy to be added with `cap`. Anyone can add it once the timelock has passed.
    function submitStrategy(IStrategy strategy, uint256 cap) external onlyCurator {
        if (_isActive(strategy)) revert AlreadySet();
        if (pendingStrategy[strategy].validAt != 0) revert AlreadyPending();
        _checkStrategy(strategy);
        uint64 validAt = _validAt();
        pendingStrategy[strategy] = Pending(cap, validAt);
        emit StrategySubmitted(strategy, cap, validAt);
    }

    function acceptStrategy(IStrategy strategy) external {
        uint256 cap = _consume(pendingStrategy[strategy]);
        delete pendingStrategy[strategy];
        _addStrategy(strategy, cap);
    }

    /// @notice A lower cap applies at once; a higher one waits for the timelock.
    function submitCap(IStrategy strategy, uint256 cap) external onlyCurator {
        uint256 current = _activeCap(strategy);
        if (cap == current) revert AlreadySet();
        if (cap < current) {
            _setCap(strategy, cap);
            return;
        }
        uint64 validAt = _validAt();
        pendingCap[strategy] = Pending(cap, validAt);
        emit CapSubmitted(strategy, cap, validAt);
    }

    function acceptCap(IStrategy strategy) external {
        _setCap(strategy, _consume(pendingCap[strategy]));
    }

    function setDepositLimit(uint256 limit) external onlyCurator {
        depositLimit = limit;
        emit DepositLimitSet(limit);
    }

    // ---------------------------------------------------------------------
    // Guardian
    // ---------------------------------------------------------------------

    function pause() external onlyGuardian {
        if (paused) revert AlreadySet();
        paused = true;
        emit PausedSet(msg.sender, true);
    }

    function unpause() external onlyOwner {
        if (!paused) revert AlreadySet();
        paused = false;
        emit PausedSet(msg.sender, false);
    }

    function revokePendingPerformanceFee() external onlyGuardian {
        _revoke(pendingPerformanceFee, "performanceFee", IStrategy(address(0)));
    }

    function revokePendingManagementFee() external onlyGuardian {
        _revoke(pendingManagementFee, "managementFee", IStrategy(address(0)));
    }

    function revokePendingTimelock() external onlyGuardian {
        _revoke(pendingTimelock, "timelock", IStrategy(address(0)));
    }

    function revokePendingGuardian() external onlyGuardian {
        _revoke(pendingGuardian, "guardian", IStrategy(address(0)));
    }

    function revokePendingStrategy(IStrategy strategy) external {
        if (msg.sender != guardian && msg.sender != curator && msg.sender != owner) revert Unauthorized();
        _revoke(pendingStrategy[strategy], "strategy", strategy);
    }

    function revokePendingCap(IStrategy strategy) external {
        if (msg.sender != guardian && msg.sender != curator && msg.sender != owner) revert Unauthorized();
        _revoke(pendingCap[strategy], "cap", strategy);
    }

    // ---------------------------------------------------------------------
    // Internal
    // ---------------------------------------------------------------------

    function _validAt() private view returns (uint64) {
        return uint64(block.timestamp + timelock);
    }

    /// @dev Returns the pending value once its timelock has passed. The caller deletes the entry.
    function _consume(Pending storage pending) private view returns (uint256) {
        if (pending.validAt == 0) revert NothingPending();
        if (block.timestamp < pending.validAt) revert TimelockNotElapsed();
        return pending.value;
    }

    function _revoke(Pending storage pending, bytes32 what, IStrategy strategy) private {
        if (pending.validAt == 0) revert NothingPending();
        delete pending.value;
        delete pending.validAt;
        emit PendingRevoked(msg.sender, what, strategy);
    }

    function _setPerformanceFee(uint256 fee) private {
        performanceFee = fee;
        delete pendingPerformanceFee;
        emit PerformanceFeeSet(fee);
    }

    /// @dev Charges the old rate up to now before the new rate applies.
    function _setManagementFee(uint256 fee) private {
        _accrueManagementFee();
        managementFee = fee;
        delete pendingManagementFee;
        emit ManagementFeeSet(fee);
    }

    function _setTimelock(uint256 newTimelock) private {
        timelock = newTimelock;
        delete pendingTimelock;
        emit TimelockSet(newTimelock);
    }

    function _setGuardian(address newGuardian) private {
        guardian = newGuardian;
        delete pendingGuardian;
        emit GuardianSet(newGuardian);
    }

    /// @dev Books the management fee owed since the last accrual.
    function _accrueManagementFee() internal virtual;

    function _isActive(IStrategy strategy) internal view virtual returns (bool);

    /// @dev Reverts if `strategy` is not active.
    function _activeCap(IStrategy strategy) internal view virtual returns (uint256);

    /// @dev Reverts if `strategy` cannot be added to this vault.
    function _checkStrategy(IStrategy strategy) internal view virtual;

    function _addStrategy(IStrategy strategy, uint256 cap) internal virtual;

    /// @dev Sets an active strategy's cap and clears any pending raise.
    function _setCap(IStrategy strategy, uint256 cap) internal virtual;
}
