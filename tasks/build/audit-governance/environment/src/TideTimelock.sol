// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

/// @title TideTimelock
/// @notice Holds the Tidewater treasury and runs governance actions after a delay.
/// @dev Only the governor schedules or cancels operations. Once an operation's delay has passed, anyone can
///      execute it, so execution never waits on a single keeper. The timelock is its own admin: changing the
///      delay or the governor takes a scheduled operation.
contract TideTimelock {
    uint256 public constant MIN_DELAY_FLOOR = 1 days;
    uint256 public constant GRACE_PERIOD = 14 days;
    uint256 internal constant DONE = 1;

    address public governor;
    uint256 public minDelay;

    /// @notice Ready time of each operation; 0 when unknown or cancelled, `DONE` once executed.
    mapping(bytes32 => uint256) public timestamps;

    event Scheduled(bytes32 indexed id, address[] targets, uint256[] values, bytes[] payloads, bytes32 salt, uint256 readyAt);
    event Executed(bytes32 indexed id);
    event Cancelled(bytes32 indexed id);
    event MinDelayChanged(uint256 oldDelay, uint256 newDelay);
    event GovernorChanged(address oldGovernor, address newGovernor);

    error NotGovernor();
    error NotTimelock();
    error AlreadyScheduled();
    error NotPending();
    error NotReady();
    error Expired();
    error DelayTooShort();
    error LengthMismatch();
    error CallFailed(uint256 index);

    modifier onlyGovernor() {
        if (msg.sender != governor) revert NotGovernor();
        _;
    }

    modifier onlySelf() {
        if (msg.sender != address(this)) revert NotTimelock();
        _;
    }

    constructor(address governor_, uint256 minDelay_) {
        if (minDelay_ < MIN_DELAY_FLOOR) revert DelayTooShort();
        governor = governor_;
        minDelay = minDelay_;
    }

    receive() external payable {}

    // ---------------------------------------------------------------------
    // Operations
    // ---------------------------------------------------------------------

    function hashOperation(address[] calldata targets, uint256[] calldata values, bytes[] calldata payloads, bytes32 salt)
        public
        pure
        returns (bytes32)
    {
        return keccak256(abi.encode(targets, values, payloads, salt));
    }

    /// @notice Schedule a batch of calls to become executable after `delay`.
    function schedule(
        address[] calldata targets,
        uint256[] calldata values,
        bytes[] calldata payloads,
        bytes32 salt,
        uint256 delay
    ) external onlyGovernor returns (bytes32 id) {
        if (targets.length != values.length || targets.length != payloads.length) revert LengthMismatch();
        if (delay < minDelay) revert DelayTooShort();
        id = hashOperation(targets, values, payloads, salt);
        if (timestamps[id] != 0) revert AlreadyScheduled();
        uint256 readyAt = block.timestamp + delay;
        timestamps[id] = readyAt;
        emit Scheduled(id, targets, values, payloads, salt, readyAt);
    }

    /// @notice Run a scheduled batch whose delay has passed and whose grace period has not.
    function execute(address[] calldata targets, uint256[] calldata values, bytes[] calldata payloads, bytes32 salt)
        external
        payable
    {
        bytes32 id = hashOperation(targets, values, payloads, salt);
        uint256 readyAt = timestamps[id];
        if (readyAt <= DONE) revert NotPending();
        if (block.timestamp < readyAt) revert NotReady();
        if (block.timestamp > readyAt + GRACE_PERIOD) revert Expired();

        timestamps[id] = DONE;
        for (uint256 i = 0; i < targets.length; ++i) {
            (bool ok,) = targets[i].call{value: values[i]}(payloads[i]);
            if (!ok) revert CallFailed(i);
        }
        emit Executed(id);
    }

    /// @notice Drop a pending operation.
    function cancel(bytes32 id) external onlyGovernor {
        if (timestamps[id] <= DONE) revert NotPending();
        delete timestamps[id];
        emit Cancelled(id);
    }

    // ---------------------------------------------------------------------
    // Views
    // ---------------------------------------------------------------------

    function isPending(bytes32 id) external view returns (bool) {
        return timestamps[id] > DONE;
    }

    function isReady(bytes32 id) external view returns (bool) {
        uint256 readyAt = timestamps[id];
        return readyAt > DONE && block.timestamp >= readyAt && block.timestamp <= readyAt + GRACE_PERIOD;
    }

    function isDone(bytes32 id) external view returns (bool) {
        return timestamps[id] == DONE;
    }

    // ---------------------------------------------------------------------
    // Self-administration
    // ---------------------------------------------------------------------

    function setMinDelay(uint256 newDelay) external onlySelf {
        if (newDelay < MIN_DELAY_FLOOR) revert DelayTooShort();
        emit MinDelayChanged(minDelay, newDelay);
        minDelay = newDelay;
    }

    function setGovernor(address newGovernor) external onlySelf {
        emit GovernorChanged(governor, newGovernor);
        governor = newGovernor;
    }
}
