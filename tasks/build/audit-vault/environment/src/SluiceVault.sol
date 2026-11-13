// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {ERC20} from "./tokens/ERC20.sol";
import {IERC20} from "./interfaces/IERC20.sol";
import {IStrategy} from "./interfaces/IStrategy.sol";
import {ISwapper} from "./interfaces/ISwapper.sol";
import {SluiceConfig} from "./SluiceConfig.sol";

/// @title SluiceVault
/// @notice An ERC-4626 vault that spreads deposits across lending strategies. Depositors hold
///         shares; allocators move idle assets into strategies and harvest them; the treasury
///         earns a performance fee on strategy profit and a yearly management fee.
/// @dev Shares use a virtual offset of 10**DECIMALS_OFFSET against the first-depositor
///      inflation attack. Strategies are valued at what their last harvest booked
///      (`IStrategy.deployedAssets`), and harvested profit reaches the share price over
///      PROFIT_UNLOCK_TIME rather than in one step.
contract SluiceVault is ERC20, SluiceConfig {
    uint256 public constant MAX_STRATEGIES = 10;
    uint256 private constant SECONDS_PER_YEAR = 365 days;
    uint8 private constant DECIMALS_OFFSET = 6;
    /// @notice How long harvested profit takes to reach the share price.
    uint256 public constant PROFIT_UNLOCK_TIME = 2 days;

    struct StrategyParams {
        bool active;
        uint256 cap;
    }

    /// @notice One step of a reallocation: move `strategy` to `targetAssets`.
    /// @dev A target of type(uint256).max supplies all free idle assets, up to the strategy's cap.
    struct Allocation {
        IStrategy strategy;
        uint256 targetAssets;
    }

    /// @notice The token depositors put in and take out.
    address public immutable asset;
    IERC20 private immutable _token;

    /// @notice Performance and management fees booked and not yet paid to the treasury.
    uint256 public accruedFees;
    /// @notice When the management fee was last charged.
    uint256 public lastFeeAccrual;
    /// @notice Harvested profit, after fees, still unlocking as of `profitLockedAt`.
    uint256 public lockedProfit;
    /// @notice When `lockedProfit` was last set. It unlocks linearly over PROFIT_UNLOCK_TIME from here.
    uint256 public profitLockedAt;

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
    event Reallocated(address indexed allocator, uint256 withdrawn, uint256 supplied);
    event Harvested(IStrategy indexed strategy, uint256 profit, uint256 loss, uint256 fee);
    event ManagementFeeAccrued(uint256 fee);
    event FeesClaimed(address indexed treasury, uint256 assets);
    event RewardsSold(IStrategy indexed strategy, address indexed reward, uint256 amount, uint256 assets);
    event WithdrawQueueSet(address indexed caller, IStrategy[] queue);

    error ZeroAmount();
    error ExceedsMaxDeposit();
    error ExceedsMaxWithdraw();
    error InsufficientLiquidity();
    error InsufficientIdle();
    error ExceedsCap();
    error TooManyStrategies();
    error StrategyActive();
    error StrategyInactive();
    error StrategyMismatch();
    error TransferFailed();
    error NoSwapper();

    constructor(
        IERC20 asset_,
        string memory name_,
        string memory symbol_,
        address owner_,
        address treasury_,
        uint256 timelock_,
        uint256 performanceFee_,
        uint256 managementFee_
    )
        ERC20(name_, symbol_, asset_.decimals() + DECIMALS_OFFSET)
        SluiceConfig(owner_, treasury_, timelock_, performanceFee_, managementFee_)
    {
        if (owner_ == address(0) || treasury_ == address(0)) revert ZeroAddress();
        asset = address(asset_);
        _token = asset_;
        lastFeeAccrual = block.timestamp;
    }

    // ---------------------------------------------------------------------
    // ERC-4626 views
    // ---------------------------------------------------------------------

    /// @notice Idle assets plus each active strategy's value as of its last harvest, less fees owed
    ///         to the treasury and profit still unlocking.
    /// @dev Booked values rather than live ones, so a market whose price moves within a block can't
    ///      move the share price. Allocators harvest about once a day.
    function totalAssets() public view returns (uint256) {
        uint256 total = _token.balanceOf(address(this));
        uint256 length = withdrawQueue.length;
        for (uint256 i; i < length; ++i) {
            total += withdrawQueue[i].deployedAssets();
        }
        uint256 reserved = accruedFees + unlockingProfit();
        return total > reserved ? total - reserved : 0;
    }

    /// @notice The part of `lockedProfit` that has not unlocked yet.
    function unlockingProfit() public view returns (uint256) {
        uint256 elapsed = block.timestamp - profitLockedAt;
        if (elapsed >= PROFIT_UNLOCK_TIME) return 0;
        return lockedProfit * (PROFIT_UNLOCK_TIME - elapsed) / PROFIT_UNLOCK_TIME;
    }

    function convertToShares(uint256 assets) public view returns (uint256) {
        return _toShares(assets, false);
    }

    function convertToAssets(uint256 shares) public view returns (uint256) {
        return _toAssets(shares, false);
    }

    function maxDeposit(address) public view returns (uint256) {
        if (paused) return 0;
        uint256 total = totalAssets();
        return total >= depositLimit ? 0 : depositLimit - total;
    }

    function maxMint(address receiver) public view returns (uint256) {
        if (!paused && depositLimit == type(uint256).max) return type(uint256).max;
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
        _accrueManagementFee();
        if (assets > maxDeposit(receiver)) revert ExceedsMaxDeposit();
        shares = previewDeposit(assets);
        if (shares == 0) revert ZeroAmount();
        _deposit(receiver, assets, shares);
    }

    function mint(uint256 shares, address receiver) external returns (uint256 assets) {
        if (shares == 0) revert ZeroAmount();
        _accrueManagementFee();
        assets = previewMint(shares);
        if (assets > maxDeposit(receiver)) revert ExceedsMaxDeposit();
        _deposit(receiver, assets, shares);
    }

    function withdraw(uint256 assets, address receiver, address account) external returns (uint256 shares) {
        if (assets == 0) revert ZeroAmount();
        _accrueManagementFee();
        if (assets > maxWithdraw(account)) revert ExceedsMaxWithdraw();
        shares = previewWithdraw(assets);
        _withdraw(receiver, account, assets, shares);
    }

    function redeem(uint256 shares, address receiver, address account) external returns (uint256 assets) {
        _accrueManagementFee();
        if (shares > maxRedeem(account)) revert ExceedsMaxWithdraw();
        assets = previewRedeem(shares);
        if (assets == 0) revert ZeroAmount();
        _withdraw(receiver, account, assets, shares);
    }

    // ---------------------------------------------------------------------
    // Allocator
    // ---------------------------------------------------------------------

    /// @notice Moves idle assets into a strategy, up to its cap. Fees owed to the treasury stay idle.
    function allocate(IStrategy strategy, uint256 assets) external onlyAllocator whenNotPaused {
        if (!strategies[strategy].active) revert StrategyInactive();
        _allocate(strategy, assets);
    }

    /// @notice Pulls assets back from a strategy into the vault's idle balance.
    function deallocate(IStrategy strategy, uint256 assets) external onlyAllocator {
        if (!strategies[strategy].active) revert StrategyInactive();
        _deallocate(strategy, assets);
    }

    /// @notice Moves each listed strategy toward its target, in order. List the strategies to take
    ///         from first so their assets are idle when the later ones are supplied.
    function reallocate(Allocation[] calldata allocations) external onlyAllocator whenNotPaused {
        uint256 withdrawn;
        uint256 supplied;
        for (uint256 i; i < allocations.length; ++i) {
            IStrategy strategy = allocations[i].strategy;
            if (!strategies[strategy].active) revert StrategyInactive();
            uint256 current = strategy.deployedAssets();
            uint256 target = allocations[i].targetAssets;
            if (target < current) {
                withdrawn += _deallocate(strategy, current - target);
            } else if (target > current) {
                uint256 assets = target == type(uint256).max ? _fillAmount(strategy, current) : target - current;
                if (assets == 0) continue;
                _allocate(strategy, assets);
                supplied += assets;
            }
        }
        emit Reallocated(msg.sender, withdrawn, supplied);
    }

    /// @notice Books a strategy's profit or loss since its last harvest and charges the
    ///         performance fee on profit.
    function harvest(IStrategy strategy) external onlyAllocator {
        if (!strategies[strategy].active) revert StrategyInactive();
        _accrueManagementFee();
        _harvest(strategy);
    }

    /// @notice Harvests every active strategy in withdrawal-queue order.
    function harvestAll() external onlyAllocator {
        _accrueManagementFee();
        uint256 length = withdrawQueue.length;
        for (uint256 i; i < length; ++i) {
            _harvest(withdrawQueue[i]);
        }
    }

    /// @notice Claims a strategy's incentive rewards and sells them for the vault's asset through
    ///         `rewardSwapper`. The proceeds stay idle for allocators to supply.
    function sellRewards(IStrategy strategy, address reward, uint256 minAssets)
        external
        onlyAllocator
        returns (uint256 assets)
    {
        if (!strategies[strategy].active) revert StrategyInactive();
        address swapper = rewardSwapper;
        if (swapper == address(0)) revert NoSwapper();
        uint256 amount = strategy.claimRewards(reward);
        if (amount == 0) revert ZeroAmount();
        if (!IERC20(reward).approve(swapper, amount)) revert TransferFailed();
        assets = ISwapper(swapper).swap(reward, asset, amount, minAssets, address(this));
        emit RewardsSold(strategy, reward, amount, assets);
    }

    /// @notice Pays booked fees to the treasury. Anyone may call.
    function claimFees() external {
        _accrueManagementFee();
        uint256 fees = accruedFees;
        if (fees == 0) revert ZeroAmount();
        _ensureIdle(fees);
        accruedFees = 0;
        if (!_token.transfer(treasury, fees)) revert TransferFailed();
        emit FeesClaimed(treasury, fees);
    }

    // ---------------------------------------------------------------------
    // Curator
    // ---------------------------------------------------------------------

    /// @notice Harvests a strategy one last time, pulls everything out of it, and drops it from the queue.
    /// @dev Reverts while the strategy's market cannot return everything; lower its cap and
    ///      deallocate first.
    function removeStrategy(IStrategy strategy) external onlyCurator {
        if (!strategies[strategy].active) revert StrategyInactive();
        _accrueManagementFee();
        _harvest(strategy);
        uint256 returned = strategy.undeployAll();
        delete strategies[strategy];
        delete pendingCap[strategy];
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
    function setWithdrawQueue(IStrategy[] calldata queue) external onlyCurator {
        uint256 length = withdrawQueue.length;
        if (queue.length != length) revert StrategyMismatch();
        for (uint256 i; i < length; ++i) {
            if (!strategies[queue[i]].active) revert StrategyInactive();
            for (uint256 j; j < i; ++j) {
                if (queue[j] == queue[i]) revert StrategyMismatch();
            }
        }
        withdrawQueue = queue;
        emit WithdrawQueueSet(msg.sender, queue);
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

    function _allocate(IStrategy strategy, uint256 assets) private {
        if (assets == 0) revert ZeroAmount();
        uint256 idle = _token.balanceOf(address(this));
        if (idle < accruedFees || assets > idle - accruedFees) revert InsufficientIdle();
        if (strategy.deployedAssets() + assets > strategies[strategy].cap) revert ExceedsCap();
        if (!_token.approve(address(strategy), assets)) revert TransferFailed();
        strategy.deploy(assets);
        emit Allocated(strategy, assets);
    }

    function _deallocate(IStrategy strategy, uint256 assets) private returns (uint256 returned) {
        returned = strategy.undeploy(assets);
        emit Deallocated(strategy, returned);
    }

    /// @dev Free idle assets (idle minus fees owed), limited by the room left under the strategy's cap.
    function _fillAmount(IStrategy strategy, uint256 current) private view returns (uint256) {
        uint256 cap = strategies[strategy].cap;
        if (current >= cap) return 0;
        uint256 idle = _token.balanceOf(address(this));
        uint256 free = idle > accruedFees ? idle - accruedFees : 0;
        uint256 room = cap - current;
        return free < room ? free : room;
    }

    /// @dev Profit after the fee joins what is still unlocking and the unlock restarts. A loss is
    ///      taken from profit still unlocking first, and the rest reaches the share price at once.
    function _harvest(IStrategy strategy) private {
        int256 delta = strategy.harvest();
        uint256 profit;
        uint256 loss;
        uint256 fee;
        uint256 unlocking = unlockingProfit();
        if (delta > 0) {
            profit = uint256(delta);
            fee = profit * performanceFee / MAX_BPS;
            accruedFees += fee;
            unlocking += profit - fee;
        } else {
            loss = uint256(-delta);
            unlocking = loss < unlocking ? unlocking - loss : 0;
        }
        lockedProfit = unlocking;
        profitLockedAt = block.timestamp;
        emit Harvested(strategy, profit, loss, fee);
    }

    /// @dev Charges `managementFee` per year on total assets for the time since the last accrual.
    function _accrueManagementFee() internal override {
        uint256 elapsed = block.timestamp - lastFeeAccrual;
        if (elapsed == 0) return;
        lastFeeAccrual = block.timestamp;
        if (managementFee == 0) return;
        uint256 fee = totalAssets() * managementFee * elapsed / (MAX_BPS * SECONDS_PER_YEAR);
        if (fee == 0) return;
        accruedFees += fee;
        emit ManagementFeeAccrued(fee);
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

    function _isActive(IStrategy strategy) internal view override returns (bool) {
        return strategies[strategy].active;
    }

    function _activeCap(IStrategy strategy) internal view override returns (uint256) {
        if (!strategies[strategy].active) revert StrategyInactive();
        return strategies[strategy].cap;
    }

    function _checkStrategy(IStrategy strategy) internal view override {
        if (strategy.vault() != address(this) || strategy.asset() != asset) revert StrategyMismatch();
    }

    function _addStrategy(IStrategy strategy, uint256 cap) internal override {
        if (strategies[strategy].active) revert StrategyActive();
        _checkStrategy(strategy);
        if (withdrawQueue.length >= MAX_STRATEGIES) revert TooManyStrategies();
        strategies[strategy] = StrategyParams({active: true, cap: cap});
        withdrawQueue.push(strategy);
        emit StrategyAdded(strategy, cap);
    }

    function _setCap(IStrategy strategy, uint256 cap) internal override {
        if (!strategies[strategy].active) revert StrategyInactive();
        strategies[strategy].cap = cap;
        delete pendingCap[strategy];
        emit StrategyCapSet(strategy, cap);
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
