#!/bin/sh
set -eu
mkdir -p /workspace/src /workspace/script
cat > /workspace/src/VoteToken.sol <<'SOL'
// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {ERC20, IERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import {ERC20Wrapper} from "@openzeppelin/contracts/token/ERC20/extensions/ERC20Wrapper.sol";
import {ERC20Votes} from "@openzeppelin/contracts/token/ERC20/extensions/ERC20Votes.sol";
import {ERC20Permit} from "@openzeppelin/contracts/token/ERC20/extensions/ERC20Permit.sol";
import {Nonces} from "@openzeppelin/contracts/utils/Nonces.sol";
import {IVoteToken} from "./interfaces/IVoteToken.sol";

contract VoteToken is ERC20Wrapper, ERC20Votes, ERC20Permit, IVoteToken {
    constructor(IERC20 underlyingToken)
        ERC20("Wrapped TOKEN", "vTOKEN") ERC20Wrapper(underlyingToken) ERC20Permit("Wrapped TOKEN") {}

    function depositFor(address account, uint256 amount) public override(ERC20Wrapper, IVoteToken) returns (bool) {
        return super.depositFor(account, amount);
    }

    function withdrawTo(address account, uint256 amount) public override(ERC20Wrapper, IVoteToken) returns (bool) {
        return super.withdrawTo(account, amount);
    }

    function decimals() public view override(ERC20, ERC20Wrapper) returns (uint8) {
        return super.decimals();
    }

    function _update(address from, address to, uint256 amount) internal override(ERC20, ERC20Votes) {
        super._update(from, to, amount);
    }

    function nonces(address owner) public view override(ERC20Permit, Nonces) returns (uint256) {
        return super.nonces(owner);
    }
}
SOL
cat > /workspace/src/TokenGovernor.sol <<'SOL'
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
SOL
cat > /workspace/script/Deploy.s.sol <<'SOL'
// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {Script} from "forge-std/Script.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {TimelockController} from "@openzeppelin/contracts/governance/TimelockController.sol";
import {VoteToken} from "../src/VoteToken.sol";
import {TokenGovernor} from "../src/TokenGovernor.sol";

contract Deploy is Script {
    function run(address token) external returns (address governorAddress, address holder) {
        vm.startBroadcast();
        (, address broadcaster,) = vm.readCallers();
        VoteToken votes = new VoteToken(IERC20(token));
        address[] memory proposers = new address[](0);
        address[] memory executors = new address[](1);
        executors[0] = address(0);
        TimelockController timelock = new TimelockController(2 days, proposers, executors, broadcaster);
        TokenGovernor governor = new TokenGovernor(votes, IERC20(token), timelock);
        timelock.grantRole(timelock.PROPOSER_ROLE(), address(governor));
        timelock.grantRole(timelock.CANCELLER_ROLE(), address(governor));
        timelock.renounceRole(timelock.DEFAULT_ADMIN_ROLE(), broadcaster);
        vm.stopBroadcast();
        return (address(governor), address(timelock));
    }
}
SOL
