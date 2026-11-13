// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {IERC20} from "./interfaces/IERC20.sol";
import {SafeTransfer} from "./libraries/SafeTransfer.sol";

/// @title BallastStaking
/// @notice BLST holders stake here to back the Ballast lending markets. Stakers earn a share of
/// protocol fees, streamed over a week, and their stake can be slashed to cover a market shortfall.
/// Leaving takes a cooldown: a staker queues a withdrawal and claims it once the cooldown ends.
/// @dev Positions are shares of the staked BLST. Rewards and slashes move the share price,
/// not the share counts.
contract BallastStaking {
    using SafeTransfer for IERC20;

    struct Withdrawal {
        address owner;
        uint64 claimableAt;
        uint128 assets;
    }

    uint256 public constant REWARD_PERIOD = 7 days;
    uint256 public constant MAX_COOLDOWN = 30 days;
    uint256 public constant MAX_SLASH_BPS = 3_000;
    uint256 public constant MIN_STAKE = 1e18;
    uint256 private constant BPS = 10_000;

    IERC20 public immutable blst;

    address public owner;
    address public pendingOwner;
    address public slasher;
    bool public paused;
    uint256 public cooldown = 10 days;

    /// @notice Shares held by each staker.
    mapping(address => uint256) public sharesOf;
    uint256 public totalShares;

    /// @notice BLST backing active shares, not counting rewards still streaming.
    uint256 public storedAssets;
    /// @notice BLST owed to queued withdrawals that have not been claimed.
    uint256 public totalQueued;

    /// @notice Current reward stream, in BLST per second.
    uint256 public rewardRate;
    uint256 public streamEnd;
    uint256 public lastUpdate;

    mapping(uint256 => Withdrawal) public withdrawals;
    uint256 public nextWithdrawalId;

    event Staked(address indexed caller, address indexed receiver, uint256 assets, uint256 shares);
    event WithdrawalQueued(uint256 indexed id, address indexed owner, uint256 shares, uint256 assets, uint256 claimableAt);
    event WithdrawalCancelled(uint256 indexed id, address indexed owner, uint256 assets, uint256 shares);
    event WithdrawalClaimed(uint256 indexed id, address indexed owner, address indexed receiver, uint256 assets);
    event Harvested(address indexed caller, uint256 added, uint256 rewardRate, uint256 streamEnd);
    event Slashed(address indexed recipient, uint256 assets);
    event SlasherSet(address indexed slasher);
    event CooldownSet(uint256 cooldown);
    event PausedSet(bool paused);
    event OwnershipTransferStarted(address indexed previousOwner, address indexed newOwner);
    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);

    error NotOwner();
    error NotSlasher();
    error Paused();
    error ZeroAddress();
    error ZeroAmount();
    error BelowMinimum();
    error InsufficientShares();
    error NotWithdrawalOwner();
    error CooldownActive();
    error UnknownWithdrawal();
    error SlashTooLarge();
    error InvalidCooldown();

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }

    modifier whenNotPaused() {
        if (paused) revert Paused();
        _;
    }

    constructor(IERC20 blst_, address owner_) {
        if (address(blst_) == address(0) || owner_ == address(0)) revert ZeroAddress();
        blst = blst_;
        owner = owner_;
        lastUpdate = block.timestamp;
        emit OwnershipTransferred(address(0), owner_);
    }

    // ---------------------------------------------------------------------
    // Views
    // ---------------------------------------------------------------------

    /// @notice BLST backing active shares, including rewards streamed so far.
    function totalAssets() public view returns (uint256) {
        return storedAssets + _vestedSinceUpdate();
    }

    /// @notice Rewards already added to the stream that have not vested yet.
    function unvestedRewards() public view returns (uint256) {
        if (block.timestamp >= streamEnd) return 0;
        return rewardRate * (streamEnd - block.timestamp);
    }

    function convertToShares(uint256 assets) public view returns (uint256) {
        uint256 shares = totalShares;
        return shares == 0 ? assets : assets * shares / totalAssets();
    }

    function convertToAssets(uint256 shares) public view returns (uint256) {
        uint256 supply = totalShares;
        return supply == 0 ? shares : shares * totalAssets() / supply;
    }

    /// @notice BLST value of an account's active shares.
    function balanceOf(address account) external view returns (uint256) {
        return convertToAssets(sharesOf[account]);
    }

    // ---------------------------------------------------------------------
    // Staking
    // ---------------------------------------------------------------------

    /// @notice Stakes `assets` BLST and credits the shares to `receiver`.
    function stake(uint256 assets, address receiver) external whenNotPaused returns (uint256 shares) {
        if (receiver == address(0)) revert ZeroAddress();
        if (assets < MIN_STAKE) revert BelowMinimum();
        _accrue();

        shares = convertToShares(assets);
        if (shares == 0) revert ZeroAmount();

        sharesOf[receiver] += shares;
        totalShares += shares;
        storedAssets += assets;

        blst.safeTransferFrom(msg.sender, address(this), assets);
        emit Staked(msg.sender, receiver, assets, shares);
    }

    /// @notice Queues `shares` for withdrawal. Their BLST value is fixed now and can be claimed
    /// after the cooldown. Queued BLST earns no further rewards.
    function requestWithdrawal(uint256 shares) external returns (uint256 id) {
        if (shares == 0) revert ZeroAmount();
        if (shares > sharesOf[msg.sender]) revert InsufficientShares();
        _accrue();

        uint256 assets = shares * storedAssets / totalShares;
        if (assets == 0) revert ZeroAmount();

        sharesOf[msg.sender] -= shares;
        totalShares -= shares;
        storedAssets -= assets;
        totalQueued += assets;

        id = nextWithdrawalId++;
        uint64 claimableAt = uint64(block.timestamp + cooldown);
        withdrawals[id] = Withdrawal({owner: msg.sender, claimableAt: claimableAt, assets: uint128(assets)});

        emit WithdrawalQueued(id, msg.sender, shares, assets, claimableAt);
    }

    /// @notice Puts a queued withdrawal back into the pool at the current share price.
    function cancelWithdrawal(uint256 id) external whenNotPaused returns (uint256 shares) {
        Withdrawal memory w = withdrawals[id];
        if (w.owner == address(0)) revert UnknownWithdrawal();
        if (w.owner != msg.sender) revert NotWithdrawalOwner();
        _accrue();

        delete withdrawals[id];
        totalQueued -= w.assets;

        shares = convertToShares(w.assets);
        sharesOf[msg.sender] += shares;
        totalShares += shares;
        storedAssets += w.assets;

        emit WithdrawalCancelled(id, msg.sender, w.assets, shares);
    }

    /// @notice Pays out a queued withdrawal once its cooldown has passed.
    function claimWithdrawal(uint256 id, address receiver) external returns (uint256 assets) {
        if (receiver == address(0)) revert ZeroAddress();
        Withdrawal memory w = withdrawals[id];
        if (w.owner == address(0)) revert UnknownWithdrawal();
        if (w.owner != msg.sender) revert NotWithdrawalOwner();
        if (block.timestamp < w.claimableAt) revert CooldownActive();

        delete withdrawals[id];
        assets = w.assets;
        totalQueued -= assets;

        blst.safeTransfer(receiver, assets);
        emit WithdrawalClaimed(id, msg.sender, receiver, assets);
    }

    // ---------------------------------------------------------------------
    // Rewards
    // ---------------------------------------------------------------------

    /// @notice Adds any BLST that reached the contract outside of staking to the reward stream.
    /// The new BLST and whatever is still streaming vest together over the next REWARD_PERIOD.
    /// @dev Anyone may call this. The FeeRouter calls it after each fee transfer.
    function harvest() external returns (uint256 added) {
        _accrue();

        uint256 remaining = unvestedRewards();
        added = blst.balanceOf(address(this)) - storedAssets - remaining;
        if (added == 0) return 0;

        rewardRate = (remaining + added) / REWARD_PERIOD;
        streamEnd = block.timestamp + REWARD_PERIOD;

        emit Harvested(msg.sender, added, rewardRate, streamEnd);
    }

    // ---------------------------------------------------------------------
    // Slashing
    // ---------------------------------------------------------------------

    /// @notice Most BLST that a single slash may take right now.
    function maxSlashable() public view returns (uint256) {
        return totalAssets() * MAX_SLASH_BPS / BPS;
    }

    /// @notice Takes `assets` BLST from stakers and sends it to `recipient` to cover a shortfall.
    /// @dev Only the ShortfallModule calls this, after its public delay.
    function slash(uint256 assets, address recipient) external {
        if (msg.sender != slasher) revert NotSlasher();
        if (recipient == address(0)) revert ZeroAddress();
        if (assets == 0) revert ZeroAmount();
        _accrue();
        if (assets > storedAssets * MAX_SLASH_BPS / BPS) revert SlashTooLarge();

        storedAssets -= assets;

        blst.safeTransfer(recipient, assets);
        emit Slashed(recipient, assets);
    }

    // ---------------------------------------------------------------------
    // Admin
    // ---------------------------------------------------------------------

    function setSlasher(address slasher_) external onlyOwner {
        if (slasher_ == address(0)) revert ZeroAddress();
        slasher = slasher_;
        emit SlasherSet(slasher_);
    }

    /// @notice Changes the cooldown for withdrawals queued from now on.
    function setCooldown(uint256 cooldown_) external onlyOwner {
        if (cooldown_ == 0 || cooldown_ > MAX_COOLDOWN) revert InvalidCooldown();
        cooldown = cooldown_;
        emit CooldownSet(cooldown_);
    }

    /// @notice Pausing stops new stake and cancellations. Queuing and claiming stay open.
    function setPaused(bool paused_) external onlyOwner {
        paused = paused_;
        emit PausedSet(paused_);
    }

    function transferOwnership(address newOwner) external onlyOwner {
        pendingOwner = newOwner;
        emit OwnershipTransferStarted(owner, newOwner);
    }

    function acceptOwnership() external {
        if (msg.sender != pendingOwner) revert NotOwner();
        emit OwnershipTransferred(owner, msg.sender);
        owner = msg.sender;
        pendingOwner = address(0);
    }

    // ---------------------------------------------------------------------
    // Internal
    // ---------------------------------------------------------------------

    function _vestedSinceUpdate() private view returns (uint256) {
        uint256 end = block.timestamp < streamEnd ? block.timestamp : streamEnd;
        if (end <= lastUpdate) return 0;
        return rewardRate * (end - lastUpdate);
    }

    function _accrue() private {
        storedAssets += _vestedSinceUpdate();
        lastUpdate = block.timestamp;
    }
}
