// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {ERC20} from "./tokens/ERC20.sol";
import {IERC20} from "./interfaces/IERC20.sol";
import {IStrategy} from "./interfaces/IStrategy.sol";

/// @title SluiceVault
/// @notice An ERC-4626 vault that spreads deposits across lending strategies. Depositors hold
///         shares; the keeper moves idle assets into strategies and harvests them; the treasury
///         earns a performance fee on strategy profit.
/// @dev Shares use a virtual offset of 10**DECIMALS_OFFSET against the first-depositor
///      inflation attack. Strategies are valued live through `IStrategy.totalAssets`.
contract SluiceVault is ERC20 {
    uint256 public constant MAX_BPS = 10_000;
    uint256 public constant MAX_PERFORMANCE_FEE = 3_000;
    uint256 public constant MAX_STRATEGIES = 10;
    uint8 private constant DECIMALS_OFFSET = 6;

    struct StrategyParams {
        bool active;
        uint256 cap;
    }

    /// @notice The token depositors put in and take out.
    address public immutable asset;
    IERC20 private immutable _token;

    address public owner;
    address public pendingOwner;
    address public keeper;
    address public treasury;

    /// @notice The treasury's share of strategy profit, in basis points.
    uint256 public performanceFee;
    /// @notice The most the vault will hold, in assets.
    uint256 public depositLimit;
    /// @notice Performance fees booked at harvest and not yet paid to the treasury.
    uint256 public accruedFees;
    bool public depositsPaused;

    mapping(IStrategy => StrategyParams) public strategies;
    /// @notice Active strategies, in the order withdrawals pull from them.
    IStrategy[] public withdrawQueue;

    event Deposit(address indexed sender, address indexed owner, uint256 assets, uint256 shares);
    event Withdraw(
        address indexed sender, address indexed receiver, address indexed owner, uint256 assets, uint256 shares
    );
    event StrategyAdded(IStrategy indexed strategy, uint256 cap);
    event StrategyRemoved(IStrategy indexed strategy, uint256 returned);
    event StrategyCapSet(IStrategy indexed strategy, uint256 cap);
    event Allocated(IStrategy indexed strategy, uint256 assets);
    event Deallocated(IStrategy indexed strategy, uint256 assets);
    event Harvested(IStrategy indexed strategy, uint256 profit, uint256 loss, uint256 fee);
    event FeesClaimed(address indexed treasury, uint256 assets);
    event PerformanceFeeSet(uint256 fee);
    event DepositLimitSet(uint256 limit);
    event DepositsPausedSet(bool paused);
    event KeeperSet(address keeper);
    event TreasurySet(address treasury);
    event OwnershipTransferStarted(address indexed owner, address indexed pendingOwner);
    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);

    error Unauthorized();
    error ZeroAmount();
    error ExceedsMaxDeposit();
    error ExceedsMaxWithdraw();
    error InsufficientLiquidity();
    error InsufficientIdle();
    error ExceedsCap();
    error FeeTooHigh();
    error TooManyStrategies();
    error StrategyActive();
    error StrategyInactive();
    error StrategyMismatch();
    error TransferFailed();

    modifier onlyOwner() {
        if (msg.sender != owner) revert Unauthorized();
        _;
    }

    modifier onlyKeeper() {
        if (msg.sender != keeper && msg.sender != owner) revert Unauthorized();
        _;
    }

    constructor(
        IERC20 asset_,
        string memory name_,
        string memory symbol_,
        address owner_,
        address keeper_,
        address treasury_,
        uint256 performanceFee_
    ) ERC20(name_, symbol_, asset_.decimals() + DECIMALS_OFFSET) {
        if (owner_ == address(0) || treasury_ == address(0)) revert ZeroAddress();
        if (performanceFee_ > MAX_PERFORMANCE_FEE) revert FeeTooHigh();
        asset = address(asset_);
        _token = asset_;
        owner = owner_;
        keeper = keeper_;
        treasury = treasury_;
        performanceFee = performanceFee_;
        depositLimit = type(uint256).max;
    }

    // ---------------------------------------------------------------------
    // ERC-4626 views
    // ---------------------------------------------------------------------

    /// @notice Idle assets plus every active strategy's live value.
    function totalAssets() public view returns (uint256 total) {
        total = _token.balanceOf(address(this));
        uint256 length = withdrawQueue.length;
        for (uint256 i; i < length; ++i) {
            total += withdrawQueue[i].totalAssets();
        }
    }

    function convertToShares(uint256 assets) public view returns (uint256) {
        return _toShares(assets, false);
    }

    function convertToAssets(uint256 shares) public view returns (uint256) {
        return _toAssets(shares, false);
    }

    function maxDeposit(address) public view returns (uint256) {
        if (depositsPaused) return 0;
        uint256 total = totalAssets();
        return total >= depositLimit ? 0 : depositLimit - total;
    }

    function maxMint(address receiver) public view returns (uint256) {
        if (!depositsPaused && depositLimit == type(uint256).max) return type(uint256).max;
        return _toShares(maxDeposit(receiver), false);
    }

    function maxWithdraw(address account) public view returns (uint256) {
        uint256 owned = _toAssets(balanceOf[account], false);
        uint256 liquid = availableLiquidity();
        return owned < liquid ? owned : liquid;
    }

    function maxRedeem(address account) public view returns (uint256) {
        uint256 owned = balanceOf[account];
        uint256 liquid = _toShares(availableLiquidity(), false);
        return owned < liquid ? owned : liquid;
    }

    function previewDeposit(uint256 assets) public view returns (uint256) {
        return _toShares(assets, false);
    }

    function previewMint(uint256 shares) public view returns (uint256) {
        return _toAssets(shares, true);
    }

    function previewWithdraw(uint256 assets) public view returns (uint256) {
        return _toShares(assets, true);
    }

    function previewRedeem(uint256 shares) public view returns (uint256) {
        return _toAssets(shares, false);
    }

    /// @notice Idle assets plus what every strategy can return right now.
    function availableLiquidity() public view returns (uint256 liquid) {
        liquid = _token.balanceOf(address(this));
        uint256 length = withdrawQueue.length;
        for (uint256 i; i < length; ++i) {
            liquid += withdrawQueue[i].maxUndeploy();
        }
    }

    function withdrawQueueLength() external view returns (uint256) {
        return withdrawQueue.length;
    }

    // ---------------------------------------------------------------------
    // ERC-4626 actions
    // ---------------------------------------------------------------------

    function deposit(uint256 assets, address receiver) external returns (uint256 shares) {
        if (assets > maxDeposit(receiver)) revert ExceedsMaxDeposit();
        shares = previewDeposit(assets);
        if (shares == 0) revert ZeroAmount();
        _deposit(receiver, assets, shares);
    }

    function mint(uint256 shares, address receiver) external returns (uint256 assets) {
        if (shares == 0) revert ZeroAmount();
        assets = previewMint(shares);
        if (assets > maxDeposit(receiver)) revert ExceedsMaxDeposit();
        _deposit(receiver, assets, shares);
    }

    function withdraw(uint256 assets, address receiver, address account) external returns (uint256 shares) {
        if (assets == 0) revert ZeroAmount();
        if (assets > maxWithdraw(account)) revert ExceedsMaxWithdraw();
        shares = previewWithdraw(assets);
        _withdraw(receiver, account, assets, shares);
    }

    function redeem(uint256 shares, address receiver, address account) external returns (uint256 assets) {
        if (shares > maxRedeem(account)) revert ExceedsMaxWithdraw();
        assets = previewRedeem(shares);
        if (assets == 0) revert ZeroAmount();
        _withdraw(receiver, account, assets, shares);
    }

    // ---------------------------------------------------------------------
    // Keeper
    // ---------------------------------------------------------------------

    /// @notice Moves idle assets into a strategy, up to its cap. Fees owed to the treasury stay idle.
    function allocate(IStrategy strategy, uint256 assets) external onlyKeeper {
        if (!strategies[strategy].active) revert StrategyInactive();
        if (assets == 0) revert ZeroAmount();
        uint256 idle = _token.balanceOf(address(this));
        if (idle < accruedFees || assets > idle - accruedFees) revert InsufficientIdle();
        if (strategy.totalAssets() + assets > strategies[strategy].cap) revert ExceedsCap();
        if (!_token.approve(address(strategy), assets)) revert TransferFailed();
        strategy.deploy(assets);
        emit Allocated(strategy, assets);
    }

    /// @notice Pulls assets back from a strategy into the vault's idle balance.
    function deallocate(IStrategy strategy, uint256 assets) external onlyKeeper {
        if (!strategies[strategy].active) revert StrategyInactive();
        uint256 returned = strategy.undeploy(assets);
        emit Deallocated(strategy, returned);
    }

    /// @notice Books a strategy's profit or loss since its last harvest and charges the
    ///         performance fee on profit.
    function harvest(IStrategy strategy) external onlyKeeper {
        if (!strategies[strategy].active) revert StrategyInactive();
        _harvest(strategy);
    }

    /// @notice Pays booked performance fees to the treasury. Anyone may call.
    function claimFees() external {
        uint256 fees = accruedFees;
        if (fees == 0) revert ZeroAmount();
        _ensureIdle(fees);
        accruedFees = 0;
        if (!_token.transfer(treasury, fees)) revert TransferFailed();
        emit FeesClaimed(treasury, fees);
    }

    // ---------------------------------------------------------------------
    // Owner
    // ---------------------------------------------------------------------

    function addStrategy(IStrategy strategy, uint256 cap) external onlyOwner {
        if (strategies[strategy].active) revert StrategyActive();
        if (strategy.vault() != address(this) || strategy.asset() != asset) revert StrategyMismatch();
        if (withdrawQueue.length >= MAX_STRATEGIES) revert TooManyStrategies();
        strategies[strategy] = StrategyParams({active: true, cap: cap});
        withdrawQueue.push(strategy);
        emit StrategyAdded(strategy, cap);
    }

    function setStrategyCap(IStrategy strategy, uint256 cap) external onlyOwner {
        if (!strategies[strategy].active) revert StrategyInactive();
        strategies[strategy].cap = cap;
        emit StrategyCapSet(strategy, cap);
    }

    /// @notice Harvests a strategy one last time, pulls everything out of it, and drops it from the queue.
    function removeStrategy(IStrategy strategy) external onlyOwner {
        if (!strategies[strategy].active) revert StrategyInactive();
        _harvest(strategy);
        uint256 returned = strategy.undeployAll();
        delete strategies[strategy];
        uint256 length = withdrawQueue.length;
        for (uint256 i; i < length; ++i) {
            if (withdrawQueue[i] == strategy) {
                withdrawQueue[i] = withdrawQueue[length - 1];
                withdrawQueue.pop();
                break;
            }
        }
        emit StrategyRemoved(strategy, returned);
    }

    /// @notice Replaces the withdrawal order. `queue` must list every active strategy exactly once.
    function setWithdrawQueue(IStrategy[] calldata queue) external onlyOwner {
        uint256 length = withdrawQueue.length;
        if (queue.length != length) revert StrategyMismatch();
        for (uint256 i; i < length; ++i) {
            if (!strategies[queue[i]].active) revert StrategyInactive();
            for (uint256 j; j < i; ++j) {
                if (queue[j] == queue[i]) revert StrategyMismatch();
            }
        }
        withdrawQueue = queue;
    }

    function setPerformanceFee(uint256 fee) external onlyOwner {
        if (fee > MAX_PERFORMANCE_FEE) revert FeeTooHigh();
        performanceFee = fee;
        emit PerformanceFeeSet(fee);
    }

    function setDepositLimit(uint256 limit) external onlyOwner {
        depositLimit = limit;
        emit DepositLimitSet(limit);
    }

    function setDepositsPaused(bool paused) external onlyOwner {
        depositsPaused = paused;
        emit DepositsPausedSet(paused);
    }

    function setKeeper(address keeper_) external onlyOwner {
        keeper = keeper_;
        emit KeeperSet(keeper_);
    }

    function setTreasury(address treasury_) external onlyOwner {
        if (treasury_ == address(0)) revert ZeroAddress();
        treasury = treasury_;
        emit TreasurySet(treasury_);
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

    function _deposit(address receiver, uint256 assets, uint256 shares) private {
        if (!_token.transferFrom(msg.sender, address(this), assets)) revert TransferFailed();
        _mint(receiver, shares);
        emit Deposit(msg.sender, receiver, assets, shares);
    }

    function _withdraw(address receiver, address account, uint256 assets, uint256 shares) private {
        if (msg.sender != account) _spendAllowance(account, msg.sender, shares);
        _burn(account, shares);
        _ensureIdle(assets);
        if (!_token.transfer(receiver, assets)) revert TransferFailed();
        emit Withdraw(msg.sender, receiver, account, assets, shares);
    }

    function _harvest(IStrategy strategy) private {
        int256 delta = strategy.harvest();
        uint256 profit;
        uint256 loss;
        uint256 fee;
        if (delta > 0) {
            profit = uint256(delta);
            fee = profit * performanceFee / MAX_BPS;
            accruedFees += fee;
        } else {
            loss = uint256(-delta);
        }
        emit Harvested(strategy, profit, loss, fee);
    }

    /// @dev Pulls from strategies in queue order until the vault holds at least `assets` idle.
    function _ensureIdle(uint256 assets) private {
        uint256 idle = _token.balanceOf(address(this));
        if (idle >= assets) return;
        uint256 length = withdrawQueue.length;
        for (uint256 i; i < length && idle < assets; ++i) {
            IStrategy strategy = withdrawQueue[i];
            uint256 available = strategy.maxUndeploy();
            if (available == 0) continue;
            uint256 needed = assets - idle;
            idle += strategy.undeploy(needed < available ? needed : available);
        }
        if (idle < assets) revert InsufficientLiquidity();
    }

    function _toShares(uint256 assets, bool roundUp) private view returns (uint256) {
        return _mulDiv(assets, totalSupply + 10 ** DECIMALS_OFFSET, totalAssets() + 1, roundUp);
    }

    function _toAssets(uint256 shares, bool roundUp) private view returns (uint256) {
        return _mulDiv(shares, totalAssets() + 1, totalSupply + 10 ** DECIMALS_OFFSET, roundUp);
    }

    function _mulDiv(uint256 x, uint256 y, uint256 d, bool roundUp) private pure returns (uint256 z) {
        z = x * y / d;
        if (roundUp && mulmod(x, y, d) > 0) z += 1;
    }
}
