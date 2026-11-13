// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {BallastStaking} from "./BallastStaking.sol";

/// @title ShortfallModule
/// @notice Governance uses this module to slash stakers when a Ballast market ends up with bad debt.
/// A slash is proposed in public, can be vetoed by the guardian during the delay, and can then be
/// executed by anyone until it expires.
contract ShortfallModule {
    struct Proposal {
        uint128 assets;
        uint64 executableAt;
        uint64 expiresAt;
        address recipient;
        bool executed;
        bool vetoed;
    }

    uint256 public constant MIN_DELAY = 1 days;
    uint256 public constant MAX_DELAY = 7 days;
    uint256 public constant EXECUTION_WINDOW = 3 days;

    BallastStaking public immutable staking;

    /// @notice The governance timelock.
    address public governance;
    /// @notice A multisig that may veto a proposed slash before it executes.
    address public guardian;
    uint256 public delay = 2 days;

    mapping(uint256 => Proposal) public proposals;
    uint256 public proposalCount;

    event SlashProposed(uint256 indexed id, uint256 assets, address indexed recipient, uint256 executableAt, string reason);
    event SlashExecuted(uint256 indexed id, uint256 assets, address indexed recipient);
    event SlashVetoed(uint256 indexed id);
    event DelaySet(uint256 delay);
    event GuardianSet(address indexed guardian);
    event GovernanceSet(address indexed governance);

    error NotGovernance();
    error NotGuardian();
    error ZeroAddress();
    error ZeroAmount();
    error InvalidDelay();
    error UnknownProposal();
    error NotExecutable();
    error ProposalClosed();

    modifier onlyGovernance() {
        if (msg.sender != governance) revert NotGovernance();
        _;
    }

    constructor(BallastStaking staking_, address governance_, address guardian_) {
        if (address(staking_) == address(0) || governance_ == address(0) || guardian_ == address(0)) {
            revert ZeroAddress();
        }
        staking = staking_;
        governance = governance_;
        guardian = guardian_;
    }

    /// @notice Proposes slashing `assets` BLST to `recipient`, usually the market that took the loss.
    function proposeSlash(uint256 assets, address recipient, string calldata reason)
        external
        onlyGovernance
        returns (uint256 id)
    {
        if (assets == 0) revert ZeroAmount();
        if (recipient == address(0)) revert ZeroAddress();

        id = ++proposalCount;
        uint64 executableAt = uint64(block.timestamp + delay);
        proposals[id] = Proposal({
            assets: uint128(assets),
            executableAt: executableAt,
            expiresAt: uint64(executableAt + EXECUTION_WINDOW),
            recipient: recipient,
            executed: false,
            vetoed: false
        });

        emit SlashProposed(id, assets, recipient, executableAt, reason);
    }

    /// @notice Executes a proposed slash. If stakers hold less than the proposal asks for, the
    /// slash takes as much as one slash may take.
    function executeSlash(uint256 id) external returns (uint256 slashed) {
        Proposal storage p = proposals[id];
        if (p.executableAt == 0) revert UnknownProposal();
        if (p.executed || p.vetoed) revert ProposalClosed();
        if (block.timestamp < p.executableAt || block.timestamp > p.expiresAt) revert NotExecutable();

        p.executed = true;
        uint256 max = staking.maxSlashable();
        slashed = p.assets < max ? p.assets : max;
        staking.slash(slashed, p.recipient);

        emit SlashExecuted(id, slashed, p.recipient);
    }

    function veto(uint256 id) external {
        if (msg.sender != guardian) revert NotGuardian();
        Proposal storage p = proposals[id];
        if (p.executableAt == 0) revert UnknownProposal();
        if (p.executed || p.vetoed) revert ProposalClosed();
        p.vetoed = true;
        emit SlashVetoed(id);
    }

    function setDelay(uint256 delay_) external onlyGovernance {
        if (delay_ < MIN_DELAY || delay_ > MAX_DELAY) revert InvalidDelay();
        delay = delay_;
        emit DelaySet(delay_);
    }

    function setGuardian(address guardian_) external onlyGovernance {
        if (guardian_ == address(0)) revert ZeroAddress();
        guardian = guardian_;
        emit GuardianSet(guardian_);
    }

    function setGovernance(address governance_) external onlyGovernance {
        if (governance_ == address(0)) revert ZeroAddress();
        governance = governance_;
        emit GovernanceSet(governance_);
    }
}
