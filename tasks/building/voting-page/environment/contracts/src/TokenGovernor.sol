// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {Governor} from "@openzeppelin/contracts/governance/Governor.sol";
import {IGovernor} from "@openzeppelin/contracts/governance/IGovernor.sol";
import {GovernorSettings} from "@openzeppelin/contracts/governance/extensions/GovernorSettings.sol";
import {GovernorVotes} from "@openzeppelin/contracts/governance/extensions/GovernorVotes.sol";
import {GovernorCountingSimple} from "@openzeppelin/contracts/governance/extensions/GovernorCountingSimple.sol";
import {GovernorPreventLateQuorum} from "@openzeppelin/contracts/governance/extensions/GovernorPreventLateQuorum.sol";
import {GovernorTimelockControl} from "@openzeppelin/contracts/governance/extensions/GovernorTimelockControl.sol";
import {TimelockController} from "@openzeppelin/contracts/governance/TimelockController.sol";
import {IVotes} from "@openzeppelin/contracts/governance/utils/IVotes.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";

contract TokenGovernor is GovernorSettings, GovernorVotes, GovernorCountingSimple,
    GovernorPreventLateQuorum, GovernorTimelockControl
{
    IERC20 public immutable underlying;

    constructor(IVotes voteToken, IERC20 token_, TimelockController timelock_)
        Governor("TOKEN Governor") GovernorSettings(7200, 50400, 0) GovernorVotes(voteToken)
        GovernorPreventLateQuorum(7200) GovernorTimelockControl(timelock_)
    {
        underlying = token_;
    }

    function quorum(uint256) public view override returns (uint256) {
        return underlying.totalSupply() * 4 / 100;
    }

    function COUNTING_MODE() public pure override(GovernorCountingSimple, IGovernor) returns (string memory) {
        return "support=bravo&quorum=for";
    }

    function _quorumReached(uint256 proposalId) internal view override(Governor, GovernorCountingSimple) returns (bool) {
        (, uint256 forVotes,) = proposalVotes(proposalId);
        return forVotes >= quorum(proposalSnapshot(proposalId));
    }

    function votingDelay() public view override(Governor, GovernorSettings) returns (uint256) {
        return super.votingDelay();
    }

    function votingPeriod() public view override(Governor, GovernorSettings) returns (uint256) {
        return super.votingPeriod();
    }

    function proposalThreshold() public view override(Governor, GovernorSettings) returns (uint256) {
        return super.proposalThreshold();
    }

    function proposalDeadline(uint256 id) public view override(Governor, GovernorPreventLateQuorum) returns (uint256) {
        return super.proposalDeadline(id);
    }

    function _tallyUpdated(uint256 id) internal override(Governor, GovernorPreventLateQuorum) {
        super._tallyUpdated(id);
    }

    function state(uint256 id) public view override(Governor, GovernorTimelockControl) returns (ProposalState) {
        return super.state(id);
    }

    function proposalNeedsQueuing(uint256 id) public view override(Governor, GovernorTimelockControl) returns (bool) {
        return super.proposalNeedsQueuing(id);
    }

    function _queueOperations(uint256 id, address[] memory targets, uint256[] memory values,
        bytes[] memory calldatas, bytes32 descriptionHash)
        internal override(Governor, GovernorTimelockControl) returns (uint48)
    {
        return super._queueOperations(id, targets, values, calldatas, descriptionHash);
    }

    function _executeOperations(uint256 id, address[] memory targets, uint256[] memory values,
        bytes[] memory calldatas, bytes32 descriptionHash) internal override(Governor, GovernorTimelockControl)
    {
        super._executeOperations(id, targets, values, calldatas, descriptionHash);
    }

    function _cancel(address[] memory targets, uint256[] memory values, bytes[] memory calldatas, bytes32 descriptionHash)
        internal override(Governor, GovernorTimelockControl) returns (uint256)
    {
        return super._cancel(targets, values, calldatas, descriptionHash);
    }

    function _executor() internal view override(Governor, GovernorTimelockControl) returns (address) {
        return super._executor();
    }
}
