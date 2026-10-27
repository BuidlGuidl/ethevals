// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {IERC5805} from "@openzeppelin/contracts/interfaces/IERC5805.sol";

/// @notice TOKEN receipts with ERC-20 transfers and the standard votes and clock interfaces.
/// @dev IERC5805 exposes getVotes, getPastVotes, getPastTotalSupply, delegates, delegate,
/// delegateBySig, clock, and CLOCK_MODE for governance clients.
interface IVoteToken is IERC20, IERC5805 {
    /// @notice Deposit TOKEN from the caller and mint an equal amount of receipts to account.
    function depositFor(address account, uint256 amount) external returns (bool);

    /// @notice Burn the caller's receipts and send an equal amount of TOKEN to account.
    function withdrawTo(address account, uint256 amount) external returns (bool);
}
