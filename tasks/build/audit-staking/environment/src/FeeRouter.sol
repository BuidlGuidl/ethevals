// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {IERC20} from "./interfaces/IERC20.sol";
import {SafeTransfer} from "./libraries/SafeTransfer.sol";
import {BallastStaking} from "./BallastStaking.sol";

/// @title FeeRouter
/// @notice Ballast markets send their BLST fees here. Anyone can call `distribute` to split the
/// balance between stakers and the treasury.
contract FeeRouter {
    using SafeTransfer for IERC20;

    uint256 public constant MIN_STAKER_BPS = 5_000;
    uint256 private constant BPS = 10_000;

    IERC20 public immutable blst;
    BallastStaking public immutable staking;

    address public owner;
    address public treasury;
    uint256 public stakerBps = 8_000;

    event Distributed(address indexed caller, uint256 toStakers, uint256 toTreasury);
    event StakerBpsSet(uint256 stakerBps);
    event TreasurySet(address indexed treasury);
    event OwnerSet(address indexed owner);

    error NotOwner();
    error ZeroAddress();
    error InvalidBps();

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }

    constructor(IERC20 blst_, BallastStaking staking_, address treasury_, address owner_) {
        if (
            address(blst_) == address(0) || address(staking_) == address(0) || treasury_ == address(0)
                || owner_ == address(0)
        ) revert ZeroAddress();
        blst = blst_;
        staking = staking_;
        treasury = treasury_;
        owner = owner_;
    }

    /// @notice Sends the stakers' share of collected fees to BallastStaking, starts streaming it,
    /// and sends the rest to the treasury.
    function distribute() external returns (uint256 toStakers, uint256 toTreasury) {
        uint256 balance = blst.balanceOf(address(this));
        if (balance == 0) return (0, 0);

        toStakers = balance * stakerBps / BPS;
        toTreasury = balance - toStakers;

        if (toStakers != 0) {
            blst.safeTransfer(address(staking), toStakers);
            staking.harvest();
        }
        if (toTreasury != 0) blst.safeTransfer(treasury, toTreasury);

        emit Distributed(msg.sender, toStakers, toTreasury);
    }

    function setStakerBps(uint256 stakerBps_) external onlyOwner {
        if (stakerBps_ < MIN_STAKER_BPS || stakerBps_ > BPS) revert InvalidBps();
        stakerBps = stakerBps_;
        emit StakerBpsSet(stakerBps_);
    }

    function setTreasury(address treasury_) external onlyOwner {
        if (treasury_ == address(0)) revert ZeroAddress();
        treasury = treasury_;
        emit TreasurySet(treasury_);
    }

    function setOwner(address owner_) external onlyOwner {
        if (owner_ == address(0)) revert ZeroAddress();
        owner = owner_;
        emit OwnerSet(owner_);
    }
}
