We're opening the testnet beta of our weekly raffle on Sepolia next week. The VRF v2.5 subscription is funded, and we'll add the contract as a consumer right after deploying. Could you review the contract? Would you ship it as is, and what would you fix before the beta?

```solidity
// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {IVRFCoordinatorV2Plus} from "@chainlink/contracts/src/v0.8/vrf/dev/interfaces/IVRFCoordinatorV2Plus.sol";
import {VRFV2PlusClient} from "@chainlink/contracts/src/v0.8/vrf/dev/libraries/VRFV2PlusClient.sol";

/// Weekly raffle: 0.01 ETH per ticket, one winner takes the pot.
/// Once a round has run for a week, anyone can call draw(), and Chainlink VRF v2.5 picks the winner.
/// No owner: the coordinator, key hash and subscription are fixed at deployment.
contract Raffle {
    event Entered(uint256 indexed round, address indexed player);
    event DrawRequested(uint256 indexed round, uint256 requestId);
    event WinnerPicked(uint256 indexed round, address indexed winner, uint256 prize);
    event Claimed(address indexed winner, uint256 amount);

    // Sepolia VRF v2.5 coordinator and its 100 gwei key hash
    IVRFCoordinatorV2Plus private constant COORDINATOR =
        IVRFCoordinatorV2Plus(0x9DdfaCa8183c41ad55329BdeeD9F6A8d53168B1B);
    bytes32 private constant KEY_HASH = 0x787d74caea10b2b357790d5b5247c2f63d1d91572a9846f780606e4d953677ae;
    uint32 private constant CALLBACK_GAS_LIMIT = 100_000;
    uint16 private constant REQUEST_CONFIRMATIONS = 3;

    uint256 public constant TICKET = 0.01 ether;
    uint256 public constant ROUND_LENGTH = 7 days;

    uint256 public immutable subscriptionId;
    uint256 public round;
    uint256 public roundStart;
    mapping(uint256 => address[]) public players;
    bool public drawing;
    uint256 public pendingRequest;
    mapping(address => uint256) public winnings;

    constructor(uint256 subId) {
        subscriptionId = subId;
        roundStart = block.timestamp;
    }

    function enter() external payable {
        require(!drawing, "draw in progress");
        require(msg.value == TICKET, "ticket is 0.01 ETH");
        players[round].push(msg.sender);
        emit Entered(round, msg.sender);
    }

    function draw() external {
        require(!drawing, "draw in progress");
        require(block.timestamp >= roundStart + ROUND_LENGTH, "round still open");
        require(players[round].length > 0, "no players");
        drawing = true;
        _requestRandomness();
    }

    function _requestRandomness() private {
        pendingRequest = COORDINATOR.requestRandomWords(
            VRFV2PlusClient.RandomWordsRequest({
                keyHash: KEY_HASH,
                subId: subscriptionId,
                requestConfirmations: REQUEST_CONFIRMATIONS,
                callbackGasLimit: CALLBACK_GAS_LIMIT,
                numWords: 1,
                extraArgs: VRFV2PlusClient._argsToBytes(VRFV2PlusClient.ExtraArgsV1({nativePayment: false}))
            })
        );
        emit DrawRequested(round, pendingRequest);
    }

    /// Called by the VRF coordinator with the random words for a request.
    function rawFulfillRandomWords(uint256 requestId, uint256[] calldata randomWords) external {
        require(msg.sender == address(COORDINATOR), "only coordinator");
        require(drawing && requestId == pendingRequest, "unexpected request");
        address[] storage entrants = players[round];
        address winner = entrants[randomWords[0] % entrants.length];
        uint256 prize = entrants.length * TICKET;
        winnings[winner] += prize;
        emit WinnerPicked(round, winner, prize);
        round += 1;
        roundStart = block.timestamp;
        drawing = false;
    }

    function claim() external {
        uint256 amount = winnings[msg.sender];
        require(amount > 0, "nothing to claim");
        winnings[msg.sender] = 0;
        emit Claimed(msg.sender, amount);
        (bool ok, ) = msg.sender.call{value: amount}("");
        require(ok, "transfer failed");
    }
}
```
