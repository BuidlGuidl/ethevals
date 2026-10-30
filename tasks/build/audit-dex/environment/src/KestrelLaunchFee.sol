// SPDX-License-Identifier: BUSL-1.1
pragma solidity 0.8.30;

import {IKestrelFeeModule} from "./interfaces/IKestrelFeeModule.sol";
import {IKestrelVault} from "./interfaces/IKestrelVault.sol";

/// @title KestrelLaunchFee
/// @notice Fee module for the launch tier. A new pool starts at a high fee that falls in a straight
///         line to the tier fee, so bots that buy a new token in its first minutes pay most of their
///         gain to the pool's liquidity providers.
contract KestrelLaunchFee is IKestrelFeeModule {
    /// @notice Highest launch fee the owner may set, in basis points.
    uint16 public constant MAX_START_FEE_BPS = 5000;

    IKestrelVault public immutable vault;
    address public owner;
    /// @notice Fee a pool charges when it is created, in basis points.
    uint16 public startFeeBps;
    /// @notice Seconds the fee takes to fall from `startFeeBps` to the tier fee.
    uint32 public decayPeriod;

    event LaunchFeeSet(uint16 startFeeBps, uint32 decayPeriod);
    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);

    error Unauthorized();
    error InvalidLaunchFee();

    constructor(IKestrelVault vault_, address owner_, uint16 startFeeBps_, uint32 decayPeriod_) {
        vault = vault_;
        owner = owner_;
        _setLaunchFee(startFeeBps_, decayPeriod_);
        emit OwnershipTransferred(address(0), owner_);
    }

    /// @inheritdoc IKestrelFeeModule
    function swapFee(bytes32 poolId) external view returns (uint256) {
        IKestrelVault.Pool memory pool = vault.getPool(poolId);
        uint256 elapsed = block.timestamp - pool.createdAt;
        uint256 start = startFeeBps;
        if (elapsed >= decayPeriod || start <= pool.feeBps) return pool.feeBps;
        return start - (start - pool.feeBps) * elapsed / decayPeriod;
    }

    function setLaunchFee(uint16 startFeeBps_, uint32 decayPeriod_) external {
        if (msg.sender != owner) revert Unauthorized();
        _setLaunchFee(startFeeBps_, decayPeriod_);
    }

    function transferOwnership(address newOwner) external {
        if (msg.sender != owner) revert Unauthorized();
        emit OwnershipTransferred(owner, newOwner);
        owner = newOwner;
    }

    function _setLaunchFee(uint16 startFeeBps_, uint32 decayPeriod_) internal {
        if (startFeeBps_ > MAX_START_FEE_BPS || decayPeriod_ == 0) revert InvalidLaunchFee();
        startFeeBps = startFeeBps_;
        decayPeriod = decayPeriod_;
        emit LaunchFeeSet(startFeeBps_, decayPeriod_);
    }
}
