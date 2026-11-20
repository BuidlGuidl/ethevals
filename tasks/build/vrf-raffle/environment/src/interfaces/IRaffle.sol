// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

/// @notice The raffle as our page sees it.
interface IRaffle {
    /// @notice The price of one ticket, in wei.
    function ticketPrice() external view returns (uint256);

    /// @notice When ticket sales close, as a timestamp.
    function salesEnd() external view returns (uint256);

    /// @notice Tickets sold so far.
    function ticketsSold() external view returns (uint256);

    /// @notice Tickets held by a buyer.
    function ticketsOf(address buyer) external view returns (uint256);

    /// @notice The winner, or the zero address while there is none.
    function winner() external view returns (address);

    /// @notice Buy count tickets at ticketPrice each.
    function buyTickets(uint256 count) external payable;

    /// @notice Ask for the randomness. Anyone, once sales have closed.
    function draw() external;

    /// @notice Name the winner and send the pot to the treasury. Anyone, once the randomness is in.
    function settle() external;

    /// @notice The winner collects the NFT.
    function claimPrize() external;

    /// @notice A buyer collects their ETH when the raffle is off.
    function claimRefund() external;
}
