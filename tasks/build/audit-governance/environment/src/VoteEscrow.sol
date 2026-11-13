// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {TideToken} from "./TideToken.sol";

/// @title VoteEscrow
/// @notice Lock TIDE for up to two years to receive voting power for Tidewater governance.
/// @dev Voting power for a lock of `amount` ending at `end` is `amount * (end - t) / MAX_LOCK` at time `t`,
///      so it falls linearly to zero at the unlock time. Every change to a lock appends a checkpoint to the
///      owner's history; the governor reads that history through `getPastVotes`.
contract VoteEscrow {
    /// @notice Lock end times are rounded down to whole weeks.
    uint256 public constant WEEK = 7 days;
    /// @notice Longest allowed lock, and the lock length that gives one vote per TIDE.
    uint256 public constant MAX_LOCK = 104 weeks;
    /// @notice Share of the time-weighted lock paid as penalty on an early exit, in basis points.
    uint256 public constant EARLY_EXIT_PENALTY_BPS = 5_000;

    struct Lock {
        uint128 amount;
        uint48 end;
    }

    /// @dev State of an account's lock from `timestamp` until the next checkpoint.
    struct Checkpoint {
        uint48 timestamp;
        uint48 end;
        uint128 amount;
    }

    TideToken public immutable tide;
    /// @notice Receives early-exit penalties. Set to the DAO timelock at deployment.
    address public immutable treasury;

    mapping(address => Lock) public locks;
    mapping(address => Checkpoint[]) private _checkpoints;
    uint256 public totalLocked;

    event LockCreated(address indexed account, uint256 amount, uint256 end);
    event LockIncreased(address indexed account, uint256 added, uint256 amount);
    event LockExtended(address indexed account, uint256 end);
    event Withdrawn(address indexed account, uint256 amount);
    event ExitedEarly(address indexed account, uint256 returned, uint256 penalty);

    error ZeroAmount();
    error LockExists();
    error NoLock();
    error LockExpired();
    error LockNotExpired();
    error BadUnlockTime();
    error FutureLookup();
    error TransferFailed();

    constructor(TideToken tide_, address treasury_) {
        tide = tide_;
        treasury = treasury_;
    }

    // ---------------------------------------------------------------------
    // Locks
    // ---------------------------------------------------------------------

    /// @notice Lock `amount` TIDE until `unlockTime`, rounded down to a whole week.
    function createLock(uint256 amount, uint256 unlockTime) external {
        if (amount == 0) revert ZeroAmount();
        if (locks[msg.sender].amount != 0) revert LockExists();
        uint256 end = (unlockTime / WEEK) * WEEK;
        if (end <= block.timestamp || end > block.timestamp + MAX_LOCK) revert BadUnlockTime();

        _pull(amount);
        Lock memory lock = Lock({amount: uint128(amount), end: uint48(end)});
        locks[msg.sender] = lock;
        totalLocked += amount;
        _writeCheckpoint(msg.sender, lock);
        emit LockCreated(msg.sender, amount, end);
    }

    /// @notice Add `amount` TIDE to an active lock without changing its end.
    function increaseAmount(uint256 amount) external {
        if (amount == 0) revert ZeroAmount();
        Lock memory lock = locks[msg.sender];
        if (lock.amount == 0) revert NoLock();
        if (lock.end <= block.timestamp) revert LockExpired();

        _pull(amount);
        lock.amount += uint128(amount);
        locks[msg.sender] = lock;
        totalLocked += amount;
        _writeCheckpoint(msg.sender, lock);
        emit LockIncreased(msg.sender, amount, lock.amount);
    }

    /// @notice Move the end of an active lock later, up to `MAX_LOCK` from now.
    function extendLock(uint256 unlockTime) external {
        Lock memory lock = locks[msg.sender];
        if (lock.amount == 0) revert NoLock();
        if (lock.end <= block.timestamp) revert LockExpired();
        uint256 end = (unlockTime / WEEK) * WEEK;
        if (end <= lock.end || end > block.timestamp + MAX_LOCK) revert BadUnlockTime();

        lock.end = uint48(end);
        locks[msg.sender] = lock;
        _writeCheckpoint(msg.sender, lock);
        emit LockExtended(msg.sender, end);
    }

    /// @notice Take back the full amount of an expired lock.
    function withdraw() external {
        Lock memory lock = locks[msg.sender];
        if (lock.amount == 0) revert NoLock();
        if (lock.end > block.timestamp) revert LockNotExpired();

        _release(msg.sender, lock.amount);
        _push(msg.sender, lock.amount);
        emit Withdrawn(msg.sender, lock.amount);
    }

    /// @notice Leave an active lock before its end, paying a penalty to the treasury.
    /// @dev The penalty is half of the lock's current voting power, so it shrinks as the end approaches.
    function exitEarly() external {
        Lock memory lock = locks[msg.sender];
        if (lock.amount == 0) revert NoLock();
        if (lock.end <= block.timestamp) revert LockExpired();

        uint256 penalty = _powerOf(lock.amount, lock.end, block.timestamp) * EARLY_EXIT_PENALTY_BPS / 10_000;
        uint256 returned = lock.amount - penalty;
        _release(msg.sender, lock.amount);
        _push(treasury, penalty);
        _push(msg.sender, returned);
        emit ExitedEarly(msg.sender, returned, penalty);
    }

    // ---------------------------------------------------------------------
    // Voting power
    // ---------------------------------------------------------------------

    /// @notice Current voting power of `account`.
    function getVotes(address account) external view returns (uint256) {
        Lock memory lock = locks[account];
        return _powerOf(lock.amount, lock.end, block.timestamp);
    }

    /// @notice Voting power of `account` at `timestamp`, which must be in the past.
    function getPastVotes(address account, uint256 timestamp) external view returns (uint256) {
        if (timestamp >= block.timestamp) revert FutureLookup();
        Checkpoint[] storage history = _checkpoints[account];

        uint256 low = 0;
        uint256 high = history.length;
        while (low < high) {
            uint256 mid = (low + high) / 2;
            if (history[mid].timestamp > timestamp) high = mid;
            else low = mid + 1;
        }
        if (high == 0) return 0;
        Checkpoint memory cp = history[high - 1];
        return _powerOf(cp.amount, cp.end, timestamp);
    }

    /// @notice Number of checkpoints recorded for `account`.
    function numCheckpoints(address account) external view returns (uint256) {
        return _checkpoints[account].length;
    }

    // ---------------------------------------------------------------------
    // Internal
    // ---------------------------------------------------------------------

    function _powerOf(uint256 amount, uint256 end, uint256 timestamp) internal pure returns (uint256) {
        if (end <= timestamp) return 0;
        return amount * (end - timestamp) / MAX_LOCK;
    }

    /// @dev Records the lock state that applies from this block on. Several writes in one block
    ///      overwrite each other so lookups see a single entry per timestamp.
    function _writeCheckpoint(address account, Lock memory lock) internal {
        Checkpoint[] storage history = _checkpoints[account];
        Checkpoint memory cp = Checkpoint({timestamp: uint48(block.timestamp), end: lock.end, amount: lock.amount});
        uint256 length = history.length;
        if (length != 0 && history[length - 1].timestamp == block.timestamp) {
            history[length - 1] = cp;
        } else {
            history.push(cp);
        }
    }

    function _release(address account, uint256 amount) internal {
        delete locks[account];
        totalLocked -= amount;
    }

    function _pull(uint256 amount) internal {
        if (!tide.transferFrom(msg.sender, address(this), amount)) revert TransferFailed();
    }

    function _push(address to, uint256 amount) internal {
        if (amount == 0) return;
        if (!tide.transfer(to, amount)) revert TransferFailed();
    }
}
