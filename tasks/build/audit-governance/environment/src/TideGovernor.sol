// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {VoteEscrow} from "./VoteEscrow.sol";
import {TideTimelock} from "./TideTimelock.sol";

/// @title TideGovernor
/// @notice Proposal and voting contract for Tidewater DAO. Votes are weighted by VoteEscrow power at each
///         proposal's snapshot; passed proposals are queued in the TideTimelock, which holds the treasury.
/// @dev Timestamps are used as the clock throughout.
contract TideGovernor {
    enum ProposalState {
        Pending,
        Active,
        Canceled,
        Defeated,
        Succeeded,
        Queued,
        Expired,
        Executed
    }

    enum VoteType {
        Against,
        For,
        Abstain
    }

    struct Proposal {
        address proposer;
        uint48 snapshot;
        uint48 deadline;
        uint48 eta;
        bool canceled;
        bool executed;
        uint256 forVotes;
        uint256 againstVotes;
        uint256 abstainVotes;
    }

    VoteEscrow public immutable escrow;
    TideTimelock public immutable timelock;
    /// @notice Security council multisig that may cancel proposals.
    address public guardian;

    uint256 public votingDelay;
    uint256 public votingPeriod;
    uint256 public proposalThreshold;
    uint256 public quorumVotes;

    mapping(uint256 => Proposal) public proposals;
    mapping(uint256 => mapping(address => bool)) public hasVoted;

    event ProposalCreated(
        uint256 indexed proposalId,
        address indexed proposer,
        address[] targets,
        uint256[] values,
        bytes[] calldatas,
        string description,
        uint256 snapshot,
        uint256 deadline
    );
    event VoteCast(address indexed voter, uint256 indexed proposalId, uint8 support, uint256 weight, string reason);
    event ProposalQueued(uint256 indexed proposalId, uint256 eta);
    event ProposalExecuted(uint256 indexed proposalId);
    event ProposalCanceled(uint256 indexed proposalId);
    event GuardianChanged(address oldGuardian, address newGuardian);
    event SettingsChanged(uint256 votingDelay, uint256 votingPeriod, uint256 proposalThreshold, uint256 quorumVotes);

    error NotTimelock();
    error NotAllowed();
    error BelowThreshold();
    error InvalidProposal();
    error ProposalExists();
    error UnknownProposal();
    error WrongState(ProposalState current);
    error AlreadyVoted();
    error InvalidVoteType();

    modifier onlyTimelock() {
        if (msg.sender != address(timelock)) revert NotTimelock();
        _;
    }

    constructor(
        VoteEscrow escrow_,
        TideTimelock timelock_,
        address guardian_,
        uint256 votingDelay_,
        uint256 votingPeriod_,
        uint256 proposalThreshold_,
        uint256 quorumVotes_
    ) {
        escrow = escrow_;
        timelock = timelock_;
        guardian = guardian_;
        votingDelay = votingDelay_;
        votingPeriod = votingPeriod_;
        proposalThreshold = proposalThreshold_;
        quorumVotes = quorumVotes_;
    }

    // ---------------------------------------------------------------------
    // Proposal lifecycle
    // ---------------------------------------------------------------------

    function hashProposal(address[] memory targets, uint256[] memory values, bytes[] memory calldatas, bytes32 descriptionHash)
        public
        pure
        returns (uint256)
    {
        return uint256(keccak256(abi.encode(targets, values, calldatas, descriptionHash)));
    }

    /// @notice Create a proposal. The proposer needs `proposalThreshold` voting power as of the previous second.
    function propose(address[] memory targets, uint256[] memory values, bytes[] memory calldatas, string memory description)
        external
        returns (uint256 proposalId)
    {
        if (targets.length == 0 || targets.length != values.length || targets.length != calldatas.length) {
            revert InvalidProposal();
        }
        if (escrow.getPastVotes(msg.sender, block.timestamp - 1) < proposalThreshold) revert BelowThreshold();

        proposalId = hashProposal(targets, values, calldatas, keccak256(bytes(description)));
        Proposal storage p = proposals[proposalId];
        if (p.snapshot != 0) revert ProposalExists();

        uint256 snapshot = block.timestamp + votingDelay;
        uint256 deadline = snapshot + votingPeriod;
        p.proposer = msg.sender;
        p.snapshot = uint48(snapshot);
        p.deadline = uint48(deadline);

        emit ProposalCreated(proposalId, msg.sender, targets, values, calldatas, description, snapshot, deadline);
    }

    /// @notice Vote on an active proposal with the caller's power at its snapshot.
    function castVote(uint256 proposalId, uint8 support) external returns (uint256) {
        return _castVote(proposalId, msg.sender, support, "");
    }

    function castVoteWithReason(uint256 proposalId, uint8 support, string calldata reason) external returns (uint256) {
        return _castVote(proposalId, msg.sender, support, reason);
    }

    /// @notice Schedule a succeeded proposal in the timelock.
    function queue(address[] memory targets, uint256[] memory values, bytes[] memory calldatas, bytes32 descriptionHash)
        external
        returns (uint256 proposalId)
    {
        proposalId = hashProposal(targets, values, calldatas, descriptionHash);
        ProposalState current = state(proposalId);
        if (current != ProposalState.Succeeded) revert WrongState(current);

        uint256 delay = timelock.minDelay();
        timelock.schedule(targets, values, calldatas, descriptionHash, delay);
        uint256 eta = block.timestamp + delay;
        proposals[proposalId].eta = uint48(eta);
        emit ProposalQueued(proposalId, eta);
    }

    /// @notice Run a queued proposal through the timelock once its delay has passed.
    function execute(address[] memory targets, uint256[] memory values, bytes[] memory calldatas, bytes32 descriptionHash)
        external
        payable
        returns (uint256 proposalId)
    {
        proposalId = hashProposal(targets, values, calldatas, descriptionHash);
        ProposalState current = state(proposalId);
        if (current != ProposalState.Queued) revert WrongState(current);

        proposals[proposalId].executed = true;
        timelock.execute{value: msg.value}(targets, values, calldatas, descriptionHash);
        emit ProposalExecuted(proposalId);
    }

    /// @notice Cancel a proposal. The proposer may cancel while it is pending; the guardian may cancel at any
    ///         point before execution.
    function cancel(address[] memory targets, uint256[] memory values, bytes[] memory calldatas, bytes32 descriptionHash)
        external
        returns (uint256 proposalId)
    {
        proposalId = hashProposal(targets, values, calldatas, descriptionHash);
        ProposalState current = state(proposalId);
        Proposal storage p = proposals[proposalId];

        if (msg.sender == guardian) {
            if (current == ProposalState.Canceled || current == ProposalState.Executed) revert WrongState(current);
        } else if (msg.sender == p.proposer) {
            if (current != ProposalState.Pending) revert WrongState(current);
        } else {
            revert NotAllowed();
        }

        p.canceled = true;
        emit ProposalCanceled(proposalId);
    }

    // ---------------------------------------------------------------------
    // Views
    // ---------------------------------------------------------------------

    function state(uint256 proposalId) public view returns (ProposalState) {
        Proposal storage p = proposals[proposalId];
        if (p.snapshot == 0) revert UnknownProposal();
        if (p.executed) return ProposalState.Executed;
        if (p.canceled) return ProposalState.Canceled;
        if (block.timestamp <= p.snapshot) return ProposalState.Pending;
        if (block.timestamp <= p.deadline) return ProposalState.Active;
        if (!_succeeded(p)) return ProposalState.Defeated;
        if (p.eta == 0) return ProposalState.Succeeded;
        if (block.timestamp > p.eta + timelock.GRACE_PERIOD()) return ProposalState.Expired;
        return ProposalState.Queued;
    }

    function proposalVotes(uint256 proposalId) external view returns (uint256 against, uint256 for_, uint256 abstain) {
        Proposal storage p = proposals[proposalId];
        return (p.againstVotes, p.forVotes, p.abstainVotes);
    }

    // ---------------------------------------------------------------------
    // Settings
    // ---------------------------------------------------------------------

    function updateSettings(uint256 votingDelay_, uint256 votingPeriod_, uint256 proposalThreshold_, uint256 quorumVotes_)
        external
        onlyTimelock
    {
        votingDelay = votingDelay_;
        votingPeriod = votingPeriod_;
        proposalThreshold = proposalThreshold_;
        quorumVotes = quorumVotes_;
        emit SettingsChanged(votingDelay_, votingPeriod_, proposalThreshold_, quorumVotes_);
    }

    /// @notice Replace the guardian. Callable by governance, or by the guardian to step down.
    function setGuardian(address newGuardian) external {
        if (msg.sender != address(timelock) && msg.sender != guardian) revert NotAllowed();
        emit GuardianChanged(guardian, newGuardian);
        guardian = newGuardian;
    }

    // ---------------------------------------------------------------------
    // Internal
    // ---------------------------------------------------------------------

    function _castVote(uint256 proposalId, address voter, uint8 support, string memory reason) internal returns (uint256 weight) {
        ProposalState current = state(proposalId);
        if (current != ProposalState.Active) revert WrongState(current);
        if (hasVoted[proposalId][voter]) revert AlreadyVoted();

        Proposal storage p = proposals[proposalId];
        weight = escrow.getPastVotes(voter, p.snapshot);
        hasVoted[proposalId][voter] = true;

        if (support == uint8(VoteType.Against)) p.againstVotes += weight;
        else if (support == uint8(VoteType.For)) p.forVotes += weight;
        else if (support == uint8(VoteType.Abstain)) p.abstainVotes += weight;
        else revert InvalidVoteType();

        emit VoteCast(voter, proposalId, support, weight, reason);
    }

    function _succeeded(Proposal storage p) internal view returns (bool) {
        return p.forVotes > p.againstVotes && p.forVotes + p.abstainVotes >= quorumVotes;
    }
}
