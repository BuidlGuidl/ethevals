// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {Ownable2StepUpgradeable} from "@openzeppelin/contracts-upgradeable/access/Ownable2StepUpgradeable.sol";
import {Token} from "./Token.sol";

/// Stake TOKEN and earn newly minted TOKEN. Runs behind a transparent proxy.
/// The owner tunes the reward rate under a cap. Anything else needs an upgrade.
contract Staking is Ownable2StepUpgradeable {
    uint256 public constant MAX_REWARD_RATE = 0.1 ether;

    Token public token;
    /// TOKEN minted per second, shared by all stakers.
    uint256 public rewardRate;
    uint256 public totalStaked;
    uint256 public rewardPerTokenStored;
    uint256 public lastUpdate;
    mapping(address => uint256) public staked;
    mapping(address => uint256) public rewardPerTokenPaid;
    mapping(address => uint256) public rewards;

    event Staked(address indexed account, uint256 amount);
    event Unstaked(address indexed account, uint256 amount);
    event Claimed(address indexed account, uint256 amount);
    event RewardRateSet(uint256 rewardRate);

    error RewardRateTooHigh();

    constructor() {
        _disableInitializers();
    }

    function initialize(Token token_, address owner_, uint256 rewardRate_) external initializer {
        __Ownable_init(owner_);
        token = token_;
        rewardRate = rewardRate_;
        lastUpdate = block.timestamp;
    }

    function rewardPerToken() public view returns (uint256) {
        if (totalStaked == 0) return rewardPerTokenStored;
        return rewardPerTokenStored + (block.timestamp - lastUpdate) * rewardRate * 1e18 / totalStaked;
    }

    function earned(address account) public view returns (uint256) {
        return staked[account] * (rewardPerToken() - rewardPerTokenPaid[account]) / 1e18 + rewards[account];
    }

    function stake(uint256 amount) external {
        _accrue(msg.sender);
        totalStaked += amount;
        staked[msg.sender] += amount;
        token.transferFrom(msg.sender, address(this), amount);
        emit Staked(msg.sender, amount);
    }

    function unstake(uint256 amount) external {
        _accrue(msg.sender);
        totalStaked -= amount;
        staked[msg.sender] -= amount;
        token.transfer(msg.sender, amount);
        emit Unstaked(msg.sender, amount);
    }

    function claim() external {
        _accrue(msg.sender);
        uint256 amount = rewards[msg.sender];
        rewards[msg.sender] = 0;
        token.mint(msg.sender, amount);
        emit Claimed(msg.sender, amount);
    }

    function setRewardRate(uint256 rewardRate_) external onlyOwner {
        if (rewardRate_ > MAX_REWARD_RATE) revert RewardRateTooHigh();
        _accrue(address(0));
        rewardRate = rewardRate_;
        emit RewardRateSet(rewardRate_);
    }

    function _accrue(address account) private {
        rewardPerTokenStored = rewardPerToken();
        lastUpdate = block.timestamp;
        if (account != address(0)) {
            rewards[account] = earned(account);
            rewardPerTokenPaid[account] = rewardPerTokenStored;
        }
    }
}
