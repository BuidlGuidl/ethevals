// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {Test, Vm} from "forge-std/Test.sol";
import {IRaffle} from "../workspace/src/interfaces/IRaffle.sol";
import {Deploy} from "../workspace/script/Deploy.s.sol";
import {VRFCoordinatorV2_5Mock} from "./chainlink/src/v0.8/vrf/mocks/VRFCoordinatorV2_5Mock.sol";

interface IERC721Receiver {
    function onERC721Received(address operator, address from, uint256 tokenId, bytes calldata data) external returns (bytes4);
}

/// @dev The prize. A plain ERC-721 with the standard transfer surface.
contract PrizeNFT {
    event Transfer(address indexed from, address indexed to, uint256 indexed tokenId);
    event Approval(address indexed owner, address indexed approved, uint256 indexed tokenId);
    event ApprovalForAll(address indexed owner, address indexed operator, bool approved);

    mapping(uint256 => address) private _owners;
    mapping(address => uint256) private _balances;
    mapping(uint256 => address) private _approvals;
    mapping(address => mapping(address => bool)) private _operators;
    uint256 private _next = 1;

    function mint(address to) external returns (uint256 id) {
        id = _next++;
        _owners[id] = to;
        _balances[to] += 1;
        emit Transfer(address(0), to, id);
    }

    function supportsInterface(bytes4 id) external pure returns (bool) {
        return id == 0x80ac58cd || id == 0x01ffc9a7;
    }

    function ownerOf(uint256 id) public view returns (address owner) {
        owner = _owners[id];
        require(owner != address(0), "no such token");
    }

    function balanceOf(address owner) external view returns (uint256) {
        return _balances[owner];
    }

    function approve(address to, uint256 id) external {
        address owner = ownerOf(id);
        require(msg.sender == owner || _operators[owner][msg.sender], "not allowed");
        _approvals[id] = to;
        emit Approval(owner, to, id);
    }

    function getApproved(uint256 id) external view returns (address) {
        return _approvals[id];
    }

    function setApprovalForAll(address operator, bool approved) external {
        _operators[msg.sender][operator] = approved;
        emit ApprovalForAll(msg.sender, operator, approved);
    }

    function isApprovedForAll(address owner, address operator) external view returns (bool) {
        return _operators[owner][operator];
    }

    function transferFrom(address from, address to, uint256 id) public {
        address owner = ownerOf(id);
        require(owner == from, "wrong owner");
        require(to != address(0), "zero address");
        require(msg.sender == owner || _approvals[id] == msg.sender || _operators[owner][msg.sender], "not allowed");
        delete _approvals[id];
        _owners[id] = to;
        _balances[from] -= 1;
        _balances[to] += 1;
        emit Transfer(from, to, id);
    }

    function safeTransferFrom(address from, address to, uint256 id) external {
        safeTransferFrom(from, to, id, "");
    }

    function safeTransferFrom(address from, address to, uint256 id, bytes memory data) public {
        transferFrom(from, to, id);
        if (to.code.length != 0) {
            require(
                IERC721Receiver(to).onERC721Received(msg.sender, from, id, data) == IERC721Receiver.onERC721Received.selector,
                "unsafe recipient"
            );
        }
    }
}

/// @dev A buyer that takes neither ETH nor NFTs. Everything but buy() reverts, and it never calls claimPrize.
contract Griefer {
    function buy(IRaffle raffle, uint256 count) external payable {
        raffle.buyTickets{value: msg.value}(count);
    }

    fallback() external payable {
        revert("Griefer: no");
    }
}

contract Forwarder {
    function forward(address target, bytes calldata data) external returns (bytes memory) {
        (bool ok, bytes memory ret) = target.call(data);
        if (!ok) {
            assembly {
                revert(add(ret, 0x20), mload(ret))
            }
        }
        return ret;
    }
}

contract RaffleTest is Test {
    uint256 constant PRICE = 0.01 ether;
    // Ethereum mainnet's 200 gwei key hash. The mock accepts any value.
    bytes32 constant KEY_HASH = 0x8077df514608a09f83e4e8d300645594e5d7234665448ba83f51a50f842bd3d9;
    // Mainnet VRF 2.5 limits from Chainlink's supported-networks page. The mock enforces none of them.
    uint16 constant MAINNET_MIN_CONFIRMATIONS = 3;
    uint16 constant MAINNET_MAX_CONFIRMATIONS = 200;
    uint32 constant MAINNET_CALLBACK_GAS_CAP = 2_500_000;
    // EIP-7825: the most gas one mainnet transaction can use.
    uint256 constant TRANSACTION_GAS_CAP = 16_777_216;
    uint256 constant ORACLE_PATIENCE = 30 days;
    // Lands on the last of 5,000 tickets under the usual word % ticketsSold, so a scan over buyers runs its full length.
    uint256 constant LAST_OF_FIVE_THOUSAND = 4_999 + 5_000 * 123_456_789_012_345_678_901_234_567_890;
    address constant STRANGER = address(0xCA11);

    bytes32 constant REQUESTED = keccak256("RandomWordsRequested(bytes32,uint256,uint256,uint256,uint16,uint32,uint32,bytes,address)");
    bytes32 constant FULFILLED = keccak256("RandomWordsFulfilled(uint256,uint256,uint256,uint96,bool,bool,bool)");

    struct Request {
        uint256 id;
        uint256 subId;
        uint16 confirmations;
        uint32 gasLimit;
        uint32 numWords;
    }

    struct Round {
        IRaffle raffle;
        address treasury;
        uint256 tokenId;
        uint256 subId;
    }

    VRFCoordinatorV2_5Mock coordinator;
    PrizeNFT nft;
    address sender;
    uint256 rounds;

    function setUp() public {
        vm.warp(1_800_000_000);
        vm.roll(1_000_000);
        coordinator = new VRFCoordinatorV2_5Mock(0.1 ether, 1 gwei, 4e15);
        nft = new PrizeNFT();
        vm.deal(address(this), 100_000 ether);
    }

    // Each check deploys from inside its own test function. Foundry gives test functions the configured
    // sender, so msg.sender inside the script, a bare vm.startBroadcast() and a broadcast with PRIVATE_KEY
    // all act as the same account, the way they do under `forge script`. That account owns the
    // subscription and the NFT, as the instruction says.
    function deploy() internal returns (Round memory round) {
        Deploy deployer = new Deploy();
        vm.startBroadcast();
        (, sender,) = vm.readCallers();
        vm.stopBroadcast();
        round.treasury = makeAddr(string.concat("treasury ", vm.toString(rounds++)));
        vm.prank(sender);
        round.subId = coordinator.createSubscription();
        coordinator.fundSubscription(round.subId, 1_000 ether);
        coordinator.fundSubscriptionWithNative{value: 100 ether}(round.subId);
        round.tokenId = nft.mint(sender);
        vm.etch(sender, type(Forwarder).runtimeCode);
        bytes memory result = Forwarder(sender).forward(
            address(deployer),
            abi.encodeWithSignature(
                "run(address,uint256,bytes32,address,uint256,address)",
                address(coordinator), round.subId, KEY_HASH, address(nft), round.tokenId, round.treasury
            )
        );
        vm.etch(sender, "");
        require(result.length >= 32, "the deploy script returned no address");
        round.raffle = IRaffle(abi.decode(result, (address)));
        assertEq(nft.ownerOf(round.tokenId), address(round.raffle), "the deploy script did not put the NFT in the raffle");
        assertEq(round.raffle.ticketPrice(), PRICE, "a ticket does not cost 0.01 ETH");
        assertApproxEqAbs(round.raffle.salesEnd(), block.timestamp + 7 days, 1 hours, "sales do not run seven days from deploy");
        assertEq(round.raffle.ticketsSold(), 0, "tickets sold before any sale");
        assertEq(round.raffle.winner(), address(0), "a winner before any draw");
    }

    function buy(IRaffle raffle, address buyer, uint256 count) internal {
        uint256 held = raffle.ticketsOf(buyer);
        uint256 sold = raffle.ticketsSold();
        vm.deal(buyer, buyer.balance + count * PRICE);
        vm.prank(buyer);
        raffle.buyTickets{value: count * PRICE}(count);
        assertEq(raffle.ticketsOf(buyer), held + count, "ticketsOf does not count the purchase");
        assertEq(raffle.ticketsSold(), sold + count, "ticketsSold does not count the purchase");
    }

    function tryBuy(IRaffle raffle, address buyer, uint256 count) internal returns (bool ok) {
        vm.deal(buyer, buyer.balance + count * PRICE);
        vm.prank(buyer);
        (ok,) = address(raffle).call{value: count * PRICE}(abi.encodeCall(IRaffle.buyTickets, (count)));
    }

    /// @dev Presses draw and returns the randomness requests the raffle made in that call.
    function draw(IRaffle raffle) internal returns (bool ok, Request[] memory made) {
        vm.recordLogs();
        (ok,) = address(raffle).call(abi.encodeCall(IRaffle.draw, ()));
        made = requests(raffle, vm.getRecordedLogs());
    }

    function trySettle(IRaffle raffle) internal returns (bool ok) {
        (ok,) = address(raffle).call(abi.encodeCall(IRaffle.settle, ()));
    }

    function tryRefund(IRaffle raffle, address who) internal returns (bool ok) {
        vm.prank(who);
        (ok,) = address(raffle).call(abi.encodeCall(IRaffle.claimRefund, ()));
    }

    function refund(IRaffle raffle, address who, uint256 expected) internal {
        uint256 before = who.balance;
        vm.prank(who);
        raffle.claimRefund();
        assertEq(who.balance - before, expected, "wrong refund amount");
    }

    function requests(IRaffle raffle, Vm.Log[] memory logs) internal view returns (Request[] memory made) {
        Request[] memory all = new Request[](logs.length);
        uint256 count;
        for (uint256 i; i < logs.length; ++i) {
            Vm.Log memory log = logs[i];
            if (log.emitter != address(coordinator) || log.topics.length != 4 || log.topics[0] != REQUESTED) continue;
            if (address(uint160(uint256(log.topics[3]))) != address(raffle)) continue;
            (uint256 id,, uint16 confirmations, uint32 gasLimit, uint32 numWords,) =
                abi.decode(log.data, (uint256, uint256, uint16, uint32, uint32, bytes));
            all[count++] = Request(id, uint256(log.topics[2]), confirmations, gasLimit, numWords);
        }
        made = new Request[](count);
        for (uint256 i; i < count; ++i) made[i] = all[i];
    }

    /// @dev Plays the oracle: answers the request with words derived from seed, under the raffle's own callback gas limit.
    /// Returns whether the raffle's callback succeeded, as the coordinator reports it.
    function fulfil(IRaffle raffle, Request memory request, uint256 seed) internal returns (bool success) {
        uint256[] memory words = new uint256[](request.numWords);
        for (uint256 i; i < words.length; ++i) words[i] = uint256(keccak256(abi.encode("vrf-raffle", seed, i)));
        return fulfilWith(raffle, request, words);
    }

    function fulfilWith(IRaffle raffle, Request memory request, uint256[] memory words) internal returns (bool success) {
        // A fulfilment is its own transaction on mainnet, so the raffle's storage starts cold.
        vm.cool(address(raffle));
        vm.recordLogs();
        coordinator.fulfillRandomWordsWithOverride(request.id, address(raffle), words);
        Vm.Log[] memory logs = vm.getRecordedLogs();
        for (uint256 i; i < logs.length; ++i) {
            Vm.Log memory log = logs[i];
            if (log.emitter != address(coordinator) || log.topics.length != 3 || log.topics[0] != FULFILLED) continue;
            if (uint256(log.topics[1]) != request.id) continue;
            (,,, success,) = abi.decode(log.data, (uint256, uint96, bool, bool, bool));
            return success;
        }
        revert("the coordinator did not report the fulfilment");
    }

    /// @dev Presses settle when the round still needs it, and measures that call's gas.
    function finish(Round memory round) internal returns (uint256 settleGas) {
        uint256 pot = round.raffle.ticketsSold() * PRICE;
        if (round.raffle.winner() != address(0) && round.treasury.balance >= pot) return 0;
        // settle() is its own transaction on mainnet, so the raffle's storage starts cold.
        vm.cool(address(round.raffle));
        uint256 before = gasleft();
        (bool ok, bytes memory reason) = address(round.raffle).call(abi.encodeCall(IRaffle.settle, ()));
        settleGas = before - gasleft();
        assertTrue(ok, string.concat("settle() reverted: ", reasonOf(reason)));
    }

    function reasonOf(bytes memory data) internal pure returns (string memory) {
        if (data.length >= 68 && bytes4(data) == bytes4(keccak256("Error(string)"))) {
            bytes memory body = new bytes(data.length - 4);
            for (uint256 i; i < body.length; ++i) body[i] = data[i + 4];
            return abi.decode(body, (string));
        }
        return data.length == 0 ? "no reason" : vm.toString(data);
    }

    function claimPrize(Round memory round, address winner) internal {
        if (nft.ownerOf(round.tokenId) != winner) {
            vm.prank(winner);
            round.raffle.claimPrize();
        }
        assertEq(nft.ownerOf(round.tokenId), winner, "the winner did not get the NFT");
    }

    function test_oneDrawAtTheRightTime() public {
        Round memory round = deploy();
        IRaffle raffle = round.raffle;
        address alice = makeAddr("alice");
        address bob = makeAddr("bob");
        buy(raffle, alice, 60);
        buy(raffle, bob, 40);

        vm.warp(raffle.salesEnd() - 1);
        (, Request[] memory early) = draw(raffle);
        assertEq(early.length, 0, "randomness was requested before sales closed");
        buy(raffle, alice, 1);

        vm.warp(raffle.salesEnd() + 1);
        (, Request[] memory first) = draw(raffle);
        assertEq(first.length, 1, "the draw did not make exactly one randomness request");

        tryBuy(raffle, STRANGER, 1);
        assertEq(raffle.ticketsSold(), 101, "a ticket sold after the randomness was requested");
        assertEq(raffle.ticketsOf(STRANGER), 0, "a late buyer got a ticket after the randomness was requested");

        (, Request[] memory pending) = draw(raffle);
        assertEq(pending.length, 0, "a second randomness request went out while the first was pending");

        assertTrue(fulfil(raffle, first[0], 1), "the callback reverted");
        finish(round);
        address winner = raffle.winner();
        assertTrue(winner != address(0), "no winner after the randomness arrived");

        (, Request[] memory redo) = draw(raffle);
        assertEq(redo.length, 0, "the raffle can be drawn again after a result");
        assertEq(raffle.winner(), winner, "the winner changed after the result");
    }

    function test_theWinnerComesFromChainlink() public {
        address[] memory winners = new address[](5);
        for (uint256 r; r < winners.length; ++r) {
            Round memory round = deploy();
            IRaffle raffle = round.raffle;
            for (uint256 i; i < 100; ++i) buy(raffle, address(uint160(0xB00000 + r * 1000 + i)), 1);

            vm.warp(raffle.salesEnd() + 1);
            (, Request[] memory made) = draw(raffle);
            assertEq(made.length, 1, "the draw did not make exactly one randomness request");
            Request memory request = made[0];
            assertEq(request.subId, round.subId, "the request did not use our subscription");
            assertGe(request.confirmations, MAINNET_MIN_CONFIRMATIONS, "fewer confirmations than mainnet's minimum of 3");
            assertLe(request.confirmations, MAINNET_MAX_CONFIRMATIONS, "more confirmations than mainnet's maximum of 200");
            assertLe(request.gasLimit, MAINNET_CALLBACK_GAS_CAP, "callback gas limit above mainnet's 2,500,000");
            assertGe(request.numWords, 1, "no random words requested");

            trySettle(raffle);
            assertEq(raffle.winner(), address(0), "a winner was named before the randomness arrived");

            uint256[] memory fake = new uint256[](request.numWords);
            vm.prank(STRANGER);
            (bool accepted,) = address(raffle).call(
                abi.encodeWithSignature("rawFulfillRandomWords(uint256,uint256[])", request.id, fake)
            );
            trySettle(raffle);
            assertEq(raffle.winner(), address(0), accepted ? "a stranger's randomness was accepted" : "a stranger's randomness named a winner");

            assertTrue(fulfil(raffle, request, r + 1), "the callback reverted");
            finish(round);
            address winner = raffle.winner();
            assertTrue(raffle.ticketsOf(winner) != 0, "the winner holds no ticket");
            winners[r] = winner;
            if (r != 0) continue;

            assertEq(round.treasury.balance, 100 * PRICE, "the treasury did not get the whole pot");
            vm.prank(STRANGER);
            (bool took,) = address(raffle).call(abi.encodeCall(IRaffle.claimPrize, ()));
            address holder = nft.ownerOf(round.tokenId);
            assertTrue(holder == address(raffle) || holder == winner, took ? "a stranger took the prize" : "the prize left the raffle for someone else");
            claimPrize(round, winner);
        }
        bool differ;
        for (uint256 r = 1; r < winners.length; ++r) differ = differ || winners[r] != winners[0];
        assertTrue(differ, "five different random words gave the same winner: the draw does not follow Chainlink's randomness");
    }

    function test_aHostileWinnerCannotBlockTheRound() public {
        Round memory round = deploy();
        IRaffle raffle = round.raffle;
        Griefer griefer = new Griefer();
        griefer.buy{value: 100 * PRICE}(raffle, 100);
        assertEq(raffle.ticketsOf(address(griefer)), 100, "ticketsOf does not count the purchase");

        vm.warp(raffle.salesEnd() + 1);
        (, Request[] memory made) = draw(raffle);
        assertEq(made.length, 1, "the draw did not make exactly one randomness request");
        assertTrue(fulfil(raffle, made[0], 7), "the callback reverted for a winner that takes neither ETH nor NFTs; VRF never retries");
        finish(round);
        assertEq(raffle.winner(), address(griefer), "the only buyer did not win");
        assertEq(round.treasury.balance, 100 * PRICE, "the treasury did not get the pot while the winner stays away");
        address holder = nft.ownerOf(round.tokenId);
        assertTrue(holder == address(raffle) || holder == address(griefer), "the NFT went to someone other than the winner");
    }

    function test_tooFewTicketsRefundsEveryone() public {
        Round memory round = deploy();
        IRaffle raffle = round.raffle;
        address alice = makeAddr("alice");
        address bob = makeAddr("bob");
        address carol = makeAddr("carol");
        buy(raffle, alice, 1);
        buy(raffle, bob, 40);
        buy(raffle, carol, 58);

        uint256 before = alice.balance;
        tryRefund(raffle, alice);
        assertEq(alice.balance, before, "a refund went out while sales were open");

        vm.warp(raffle.salesEnd() + 1);
        (, Request[] memory made) = draw(raffle);
        trySettle(raffle);
        assertEq(made.length, 0, "randomness was requested for a raffle that is off");
        assertEq(raffle.winner(), address(0), "99 tickets produced a winner");

        refund(raffle, alice, 1 * PRICE);
        refund(raffle, bob, 40 * PRICE);
        refund(raffle, carol, 58 * PRICE);

        before = alice.balance;
        tryRefund(raffle, alice);
        assertEq(alice.balance, before, "a buyer was refunded twice");
        before = STRANGER.balance;
        tryRefund(raffle, STRANGER);
        assertEq(STRANGER.balance, before, "a stranger was refunded");
        assertEq(round.treasury.balance, 0, "the treasury was paid for a raffle that is off");
        assertEq(address(raffle).balance, 0, "ETH is left in the raffle after every refund");
        address holder = nft.ownerOf(round.tokenId);
        assertTrue(holder == address(raffle) || holder == sender, "the NFT left for a stranger");
    }

    function test_aSilentOracleDoesNotStrandThePot() public {
        Round memory round = deploy();
        IRaffle raffle = round.raffle;
        address alice = makeAddr("alice");
        address bob = makeAddr("bob");
        buy(raffle, alice, 50);
        buy(raffle, bob, 100);

        vm.warp(raffle.salesEnd() + 1);
        (, Request[] memory made) = draw(raffle);
        assertEq(made.length, 1, "the draw did not make exactly one randomness request");
        Request memory stale = made[0];

        // The oracle is slow, not dead. Nothing gives up yet.
        assertNobodyGivesUp(round, alice, "right after the request");
        vm.warp(block.timestamp + 1 hours);
        assertNobodyGivesUp(round, alice, "one hour after the request");

        // Thirty days of silence. Either the buyers get their ETH back, or the draw can be asked again.
        vm.warp(block.timestamp + ORACLE_PATIENCE);
        uint256 before = alice.balance;
        tryRefund(raffle, alice);
        if (alice.balance == before) {
            trySettle(raffle);
            tryRefund(raffle, alice);
        }
        Request[] memory fresh;
        if (alice.balance == before) {
            (, fresh) = draw(raffle);
            if (fresh.length == 0) tryRefund(raffle, alice);
        }
        if (alice.balance != before) {
            assertEq(alice.balance - before, 50 * PRICE, "wrong refund amount after the oracle went silent");
            refund(raffle, bob, 100 * PRICE);
            assertEq(raffle.winner(), address(0), "a winner was named without randomness");
            assertEq(round.treasury.balance, 0, "the treasury was paid for a raffle that is off");
            assertEq(address(raffle).balance, 0, "ETH is left in the raffle after every refund");
            return;
        }
        assertEq(fresh.length, 1, "after thirty days of silence nobody can get a refund and nobody can draw again: the pot is stranded");

        // The request the raffle gave up on must not decide it.
        fulfil(raffle, stale, 11);
        trySettle(raffle);
        assertEq(raffle.winner(), address(0), "the request the raffle gave up on named the winner");

        assertTrue(fulfil(raffle, fresh[0], 12), "the callback reverted");
        finish(round);
        address winner = raffle.winner();
        assertTrue(winner == alice || winner == bob, "the winner is not a buyer");
        assertEq(round.treasury.balance, 150 * PRICE, "the treasury did not get the whole pot");
        claimPrize(round, winner);
    }

    function assertNobodyGivesUp(Round memory round, address buyer, string memory when) internal {
        IRaffle raffle = round.raffle;
        (, Request[] memory again) = draw(raffle);
        assertEq(again.length, 0, string.concat("a new randomness request went out ", when));
        trySettle(raffle);
        assertEq(raffle.winner(), address(0), string.concat("a winner appeared without randomness ", when));
        uint256 before = buyer.balance;
        tryRefund(raffle, buyer);
        assertEq(buyer.balance, before, string.concat("a refund went out ", when));
        assertEq(round.treasury.balance, 0, string.concat("the treasury was paid ", when));
    }

    function test_thousandsOfBuyersStillDraw() public {
        Round memory round = deploy();
        IRaffle raffle = round.raffle;
        uint256 buyers = 5_000;
        for (uint256 i; i < buyers; ++i) buy(raffle, address(uint160(0xA00000 + i)), 1);

        vm.warp(raffle.salesEnd() + 1);
        (, Request[] memory made) = draw(raffle);
        assertEq(made.length, 1, "the draw did not make exactly one randomness request");
        assertLe(made[0].gasLimit, MAINNET_CALLBACK_GAS_CAP, "callback gas limit above mainnet's 2,500,000");
        uint256[] memory words = new uint256[](made[0].numWords);
        for (uint256 i; i < words.length; ++i) words[i] = i == 0 ? LAST_OF_FIVE_THOUSAND : uint256(keccak256(abi.encode("vrf-raffle", i)));
        assertTrue(fulfilWith(raffle, made[0], words), "the callback failed with 5,000 buyers under its own gas limit; VRF never retries");
        uint256 used = finish(round);
        assertLt(used, TRANSACTION_GAS_CAP, "settling 5,000 buyers does not fit in one mainnet transaction");
        address winner = raffle.winner();
        assertEq(raffle.ticketsOf(winner), 1, "the winner is not a buyer");
        assertEq(round.treasury.balance, buyers * PRICE, "the treasury did not get the whole pot");
        claimPrize(round, winner);
    }
}
