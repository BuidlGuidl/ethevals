#!/bin/sh
set -eu
mkdir -p /workspace/src /workspace/script
cat > /workspace/src/Raffle.sol <<'SOL'
// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {VRFConsumerBaseV2Plus} from "@chainlink/contracts/src/v0.8/vrf/dev/VRFConsumerBaseV2Plus.sol";
import {VRFV2PlusClient} from "@chainlink/contracts/src/v0.8/vrf/dev/libraries/VRFV2PlusClient.sol";
import {IERC721} from "@openzeppelin/contracts/token/ERC721/IERC721.sol";
import {IERC721Receiver} from "@openzeppelin/contracts/token/ERC721/IERC721Receiver.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import {IRaffle} from "./interfaces/IRaffle.sol";

/// @notice One NFT, 0.01 ETH tickets for seven days, one winner from Chainlink VRF 2.5.
/// The callback only stores the random word. Anyone settles, the winner and buyers pull.
contract Raffle is IRaffle, IERC721Receiver, VRFConsumerBaseV2Plus, ReentrancyGuard {
    enum State {
        Open, // selling tickets
        Drawing, // randomness requested, waiting for the oracle
        Drawn, // random word stored, waiting for settle()
        Settled, // winner named, pot paid
        Off // too few tickets, or the oracle never answered
    }

    struct Purchase {
        address buyer;
        uint256 upTo; // tickets sold after this purchase, so tickets [previous upTo, upTo) are the buyer's
    }

    uint256 public constant TICKET_PRICE = 0.01 ether;
    uint256 public constant MIN_TICKETS = 100;
    uint256 public constant SALES_PERIOD = 7 days;
    /// @dev Chainlink expires an unfunded request after 24 hours. After two days of silence the raffle is off.
    uint256 public constant ORACLE_TIMEOUT = 2 days;
    uint16 public constant REQUEST_CONFIRMATIONS = 3;
    uint32 public constant CALLBACK_GAS_LIMIT = 100_000;
    uint32 public constant NUM_WORDS = 1;

    IERC721 public immutable nft;
    uint256 public immutable tokenId;
    address public immutable treasury;
    uint256 public immutable subscriptionId;
    bytes32 public immutable keyHash;
    uint256 public immutable override salesEnd;

    State public state;
    uint256 public override ticketsSold;
    address public override winner;
    uint256 public requestId;
    uint256 public requestedAt;
    uint256 public potOwedToTreasury;
    uint256 private _randomWord;
    Purchase[] private _purchases;
    mapping(address => uint256) private _tickets;

    event TicketsBought(address indexed buyer, uint256 count);
    event DrawRequested(uint256 indexed requestId);
    event RandomnessReceived(uint256 indexed requestId);
    event Settled(address indexed winner, uint256 pot);
    event CalledOff();
    event PrizeClaimed(address indexed to);
    event Refunded(address indexed buyer, uint256 amount);

    constructor(address coordinator, uint256 subId, bytes32 keyHash_, address nft_, uint256 tokenId_, address treasury_)
        VRFConsumerBaseV2Plus(coordinator)
    {
        require(treasury_ != address(0), "no treasury");
        nft = IERC721(nft_);
        tokenId = tokenId_;
        treasury = treasury_;
        subscriptionId = subId;
        keyHash = keyHash_;
        salesEnd = block.timestamp + SALES_PERIOD;
    }

    function ticketPrice() external pure override returns (uint256) {
        return TICKET_PRICE;
    }

    function ticketsOf(address buyer) external view override returns (uint256) {
        return _tickets[buyer];
    }

    function buyTickets(uint256 count) external payable override {
        require(state == State.Open && block.timestamp < salesEnd, "sales closed");
        require(count > 0, "no tickets");
        require(msg.value == count * TICKET_PRICE, "wrong payment");
        require(nft.ownerOf(tokenId) == address(this), "prize not in escrow");
        ticketsSold += count;
        _tickets[msg.sender] += count;
        _purchases.push(Purchase(msg.sender, ticketsSold));
        emit TicketsBought(msg.sender, count);
    }

    /// @notice Anyone, once sales have closed. Asks Chainlink once, or calls the raffle off with too few tickets.
    function draw() external override nonReentrant {
        require(block.timestamp >= salesEnd, "sales still open");
        require(state == State.Open, "already drawn");
        if (ticketsSold < MIN_TICKETS) {
            _callOff();
            return;
        }
        state = State.Drawing;
        requestedAt = block.timestamp;
        requestId = s_vrfCoordinator.requestRandomWords(
            VRFV2PlusClient.RandomWordsRequest({
                keyHash: keyHash,
                subId: subscriptionId,
                requestConfirmations: REQUEST_CONFIRMATIONS,
                callbackGasLimit: CALLBACK_GAS_LIMIT,
                numWords: NUM_WORDS,
                extraArgs: VRFV2PlusClient._argsToBytes(VRFV2PlusClient.ExtraArgsV1({nativePayment: false}))
            })
        );
        emit DrawRequested(requestId);
    }

    /// @dev Only stores the word. Never reverts: the coordinator does not retry. Ignores anything but the live request.
    function fulfillRandomWords(uint256 id, uint256[] calldata randomWords) internal override {
        if (state != State.Drawing || id != requestId) return;
        _randomWord = randomWords[0];
        state = State.Drawn;
        emit RandomnessReceived(id);
    }

    /// @notice Anyone, once the randomness is in. Names the winner and pays the treasury.
    function settle() external override nonReentrant {
        require(state == State.Drawn, "randomness not in");
        state = State.Settled;
        winner = _ticketOwner(_randomWord % ticketsSold);
        uint256 pot = ticketsSold * TICKET_PRICE;
        emit Settled(winner, pot);
        (bool ok,) = treasury.call{value: pot}("");
        if (!ok) potOwedToTreasury = pot; // a treasury that cannot take ETH right now collects it through payTreasury
    }

    /// @notice Retries the treasury payment if settle() could not deliver it.
    function payTreasury() external nonReentrant {
        uint256 owed = potOwedToTreasury;
        require(owed > 0, "nothing owed");
        potOwedToTreasury = 0;
        (bool ok,) = treasury.call{value: owed}("");
        require(ok, "treasury refused");
    }

    function claimPrize() external override nonReentrant {
        require(state == State.Settled, "no winner yet");
        require(msg.sender == winner, "not the winner");
        emit PrizeClaimed(msg.sender);
        nft.safeTransferFrom(address(this), msg.sender, tokenId);
    }

    function claimRefund() external override nonReentrant {
        _callOffIfDue();
        require(state == State.Off, "raffle is on");
        uint256 count = _tickets[msg.sender];
        require(count > 0, "nothing to refund");
        _tickets[msg.sender] = 0;
        uint256 amount = count * TICKET_PRICE;
        emit Refunded(msg.sender, amount);
        (bool ok,) = msg.sender.call{value: amount}("");
        require(ok, "refund failed");
    }

    /// @notice Sends the NFT back to the organizer once the raffle is off. Anyone can trigger it.
    function returnPrize() external nonReentrant {
        _callOffIfDue();
        require(state == State.Off, "raffle is on");
        nft.safeTransferFrom(address(this), owner(), tokenId);
    }

    function onERC721Received(address, address, uint256, bytes calldata) external pure override returns (bytes4) {
        return IERC721Receiver.onERC721Received.selector;
    }

    /// @dev The raffle is off once sales closed short of 100 tickets, or the oracle stayed silent for ORACLE_TIMEOUT.
    function _callOffIfDue() internal {
        if (state == State.Open && block.timestamp >= salesEnd && ticketsSold < MIN_TICKETS) _callOff();
        else if (state == State.Drawing && block.timestamp >= requestedAt + ORACLE_TIMEOUT) _callOff();
    }

    function _callOff() internal {
        state = State.Off;
        emit CalledOff();
    }

    /// @dev Binary search over purchases: the first one whose upTo exceeds the ticket index owns it.
    function _ticketOwner(uint256 ticket) internal view returns (address) {
        uint256 low = 0;
        uint256 high = _purchases.length - 1;
        while (low < high) {
            uint256 mid = (low + high) / 2;
            if (_purchases[mid].upTo > ticket) high = mid;
            else low = mid + 1;
        }
        return _purchases[low].buyer;
    }
}
SOL
cat > /workspace/script/Deploy.s.sol <<'SOL'
// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {Script} from "forge-std/Script.sol";
import {IERC721} from "@openzeppelin/contracts/token/ERC721/IERC721.sol";
import {IVRFSubscriptionV2Plus} from "@chainlink/contracts/src/v0.8/vrf/dev/interfaces/IVRFSubscriptionV2Plus.sol";
import {Raffle} from "../src/Raffle.sol";

/// @notice Run from the wallet that holds the NFT and owns the VRF subscription.
contract Deploy is Script {
    function run(address coordinator, uint256 subId, bytes32 keyHash, address nft, uint256 tokenId, address treasury)
        external
        returns (address)
    {
        vm.startBroadcast();
        (, address broadcaster,) = vm.readCallers();
        Raffle raffle = new Raffle(coordinator, subId, keyHash, nft, tokenId, treasury);
        IVRFSubscriptionV2Plus(coordinator).addConsumer(subId, address(raffle));
        IERC721(nft).transferFrom(broadcaster, address(raffle), tokenId);
        vm.stopBroadcast();
        return address(raffle);
    }
}
SOL
