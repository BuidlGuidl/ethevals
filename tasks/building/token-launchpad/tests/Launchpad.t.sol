// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {Test} from "forge-std/Test.sol";
import {Launchpad} from "../workspace/src/Launchpad.sol";
import {MainnetCode} from "./MainnetCode.sol";

interface Pad {
    function create(string calldata name, string calldata symbol) external returns (address);
    function buy(address token) external payable;
    function sell(address token, uint256 amount) external;
    function claimFees(address token) external;
    function graduate(address token) external;
}

interface Coin {
    function balanceOf(address account) external view returns (uint256);
    function totalSupply() external view returns (uint256);
    function approve(address spender, uint256 amount) external returns (bool);
    function transfer(address to, uint256 amount) external returns (bool);
}

interface WrappedETH is Coin {
    function deposit() external payable;
    function withdraw(uint256 amount) external;
}

interface Factory {
    function getPair(address a, address b) external view returns (address);
    function createPair(address a, address b) external returns (address);
}

interface Pair is Coin {
    function token0() external view returns (address);
    function getReserves() external view returns (uint112, uint112, uint32);
    function sync() external;
    function swap(uint256 out0, uint256 out1, address to, bytes calldata data) external;
}

contract LaunchpadTest is Test {
    Factory constant FACTORY = Factory(0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f);
    WrappedETH constant WETH = WrappedETH(0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2);
    address constant ROUTER = 0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D;
    address constant DEAD = 0x000000000000000000000000000000000000dEaD;
    Pad pad;
    address creator;
    address buyer;
    address stranger;

    struct Purchase {
        uint256 spent;
        uint256 received;
    }

    function setUp() public {
        vm.chainId(1);
        vm.etch(address(FACTORY), MainnetCode.factory());
        vm.store(address(FACTORY), bytes32(uint256(1)), bytes32(uint256(uint160(0x1a9C8182C09F50C8318d769245beA52c32BE35BC))));
        vm.etch(ROUTER, MainnetCode.router());
        vm.etch(address(WETH), MainnetCode.weth());
        vm.store(address(WETH), bytes32(uint256(0)), bytes32("Wrapped Ether") | bytes32(uint256(26)));
        vm.store(address(WETH), bytes32(uint256(1)), bytes32("WETH") | bytes32(uint256(8)));
        vm.store(address(WETH), bytes32(uint256(2)), bytes32(uint256(18)));
        creator = makeAddr("creator");
        buyer = makeAddr("buyer");
        stranger = makeAddr("stranger");
        vm.deal(creator, 100 ether);
        vm.deal(buyer, 100 ether);
        vm.deal(stranger, 100 ether);
        pad = Pad(address(new Launchpad()));
    }

    function create() internal returns (address token) {
        vm.prank(creator);
        token = pad.create("Community", "COM");
    }

    function buy(address token, address who, uint256 amount) internal returns (Purchase memory p) {
        uint256 ethBefore = who.balance;
        uint256 tokensBefore = Coin(token).balanceOf(who);
        vm.prank(who);
        pad.buy{value: amount}(token);
        p.spent = ethBefore - who.balance;
        p.received = Coin(token).balanceOf(who) - tokensBefore;
        assertGt(p.spent, 0, "buy must accept ETH");
        assertGt(p.received, 0, "buy must deliver tokens");
    }

    function reserves(address token) internal view returns (uint256 ethReserve, uint256 tokenReserve) {
        address pair = FACTORY.getPair(token, address(WETH));
        if (pair == address(0)) return (0, 0);
        (uint112 r0, uint112 r1,) = Pair(pair).getReserves();
        return Pair(pair).token0() == token ? (uint256(r1), uint256(r0)) : (uint256(r0), uint256(r1));
    }

    function fill(address token) internal returns (Purchase memory last) {
        for (uint256 i; i < 64; ++i) {
            uint256 ethBefore = buyer.balance;
            uint256 tokensBefore = Coin(token).balanceOf(buyer);
            vm.prank(buyer);
            try pad.buy{value: 0.5 ether}(token) {
                uint256 received = Coin(token).balanceOf(buyer) - tokensBefore;
                if (received != 0) last = Purchase(ethBefore - buyer.balance, received);
            } catch {}
            vm.prank(stranger);
            try pad.graduate(token) {} catch {}
            (uint256 ethReserve,) = reserves(token);
            if (ethReserve >= 9 ether) {
                assertGt(last.received, 0, "graduation needs an observed final buy");
                return last;
            }
        }
        assertTrue(false, "graduation must place the raise in the pair");
    }

    function openingPrice(address token, Purchase memory last) internal view {
        (uint256 ethReserve, uint256 tokenReserve) = reserves(token);
        assertGe(ethReserve, 9 ether, "pool must hold the curve's ETH");
        assertGt(tokenReserve, 0, "pool must hold launch tokens");
        // Compare prices without assuming the token's decimals or curve formula.
        uint256 poolPrice = ethReserve * last.received;
        uint256 lastPrice = last.spent * tokenReserve;
        assertGe(poolPrice * 100, lastPrice * 80, "pool opens below the curve price");
        assertLe(poolPrice * 100, lastPrice * 125, "pool opens above the curve price");
    }

    function pairFor(address token) internal returns (address pair) {
        pair = FACTORY.getPair(token, address(WETH));
        if (pair == address(0)) pair = FACTORY.createPair(token, address(WETH));
    }

    function donateWETH(address pair, uint256 amount) internal {
        vm.startPrank(stranger);
        WETH.deposit{value: amount}();
        WETH.transfer(pair, amount);
        vm.stopPrank();
    }

    function donateTokens(address token, address pair, uint256 amount) internal {
        vm.prank(stranger);
        try Coin(token).transfer(pair, amount) {} catch {}
    }

    function sellAll(address token, address who) internal returns (uint256 received) {
        uint256 amount = Coin(token).balanceOf(who);
        vm.startPrank(who);
        Coin(token).approve(address(pad), amount);
        uint256 before = who.balance;
        pad.sell(token, amount);
        vm.stopPrank();
        received = who.balance - before;
        assertEq(Coin(token).balanceOf(who), 0, "seller must return every token");
        assertGt(received, 0, "seller must receive ETH");
    }

    function test_opensAtCurvePrice() public {
        address token = create();
        openingPrice(token, fill(token));
    }

    function test_wethSyncedIntoPair() public {
        address token = create();
        address pair = pairFor(token);
        donateWETH(pair, 1);
        try Pair(pair).sync() {} catch {}
        openingPrice(token, fill(token));
    }

    function test_tokensSyncedIntoPair() public {
        address token = create();
        buy(token, stranger, 0.5 ether);
        address pair = pairFor(token);
        donateTokens(token, pair, Coin(token).balanceOf(stranger) / 2);
        try Pair(pair).sync() {} catch {}
        openingPrice(token, fill(token));
    }

    function openingSequence(address token, bool seeded) internal returns (uint256) {
        for (uint256 i; i < 18; ++i) buy(token, buyer, 0.5 ether);
        Purchase memory attackBuy = buy(token, stranger, 0.5 ether);
        address pair = pairFor(token);
        if (seeded) {
            donateTokens(token, pair, attackBuy.received / 1e12);
            donateWETH(pair, 0.1 ether);
            try Pair(pair).sync() {} catch {}
        }
        Purchase memory last = fill(token);
        // Record the price, then execute the attack even when that price is wrong.
        (uint256 ethReserve, uint256 tokenReserve) = reserves(token);
        uint256 amount = Coin(token).balanceOf(stranger);
        uint256 out = amount * 997 * ethReserve / (tokenReserve * 1000 + amount * 997);
        vm.startPrank(stranger);
        Coin(token).transfer(pair, amount);
        if (Pair(pair).token0() == token) Pair(pair).swap(0, out, stranger, "");
        else Pair(pair).swap(out, 0, stranger, "");
        WETH.withdraw(WETH.balanceOf(stranger));
        vm.stopPrank();
        assertGe(ethReserve * last.received * 100, last.spent * tokenReserve * 80, "pool opens below the curve price");
        assertLe(ethReserve * last.received * 100, last.spent * tokenReserve * 125, "pool opens above the curve price");
        return stranger.balance;
    }

    function test_strangerCannotSetOpeningPrice() public {
        address token = create();
        uint256 snapshot = vm.snapshotState();
        uint256 controlETH = openingSequence(token, false);
        assertTrue(vm.revertToState(snapshot), "restore the control's starting state");
        uint256 seededETH = openingSequence(token, true);
        assertLe(seededETH, controlETH, "stranger profits from the seeded opening price");
    }

    function test_curveStopsAfterGraduation() public {
        address token = create();
        fill(token);
        vm.startPrank(buyer);
        Coin(token).approve(address(pad), Coin(token).balanceOf(buyer));
        uint256 ethBefore = buyer.balance;
        uint256 tokensBefore = Coin(token).balanceOf(buyer);
        try pad.buy{value: 0.1 ether}(token) {} catch {}
        assertEq(buyer.balance, ethBefore, "closed curve buy changes no ETH");
        assertEq(Coin(token).balanceOf(buyer), tokensBefore, "closed curve buy changes no tokens");
        try pad.sell(token, tokensBefore / 10) {} catch {}
        assertEq(buyer.balance, ethBefore, "closed curve sale changes no ETH");
        assertEq(Coin(token).balanceOf(buyer), tokensBefore, "closed curve sale changes no tokens");
        vm.stopPrank();
    }

    function test_lpIsBurned() public {
        address token = create();
        fill(token);
        Coin lp = Coin(FACTORY.getPair(token, address(WETH)));
        assertGt(lp.totalSupply(), 1000, "graduation must mint LP");
        assertEq(lp.balanceOf(address(0)) + lp.balanceOf(DEAD), lp.totalSupply(), "all LP must be burned");
        assertEq(lp.balanceOf(address(pad)), 0, "launchpad keeps no LP");
        assertEq(lp.balanceOf(creator), 0, "creator keeps no LP");
        assertEq(lp.balanceOf(buyer), 0, "buyer keeps no LP");
        assertEq(lp.balanceOf(stranger), 0, "graduation caller keeps no LP");
        assertEq(lp.balanceOf(address(this)), 0, "test keeps no LP");
    }

    function test_creatorEarnsFees() public {
        address token = create();
        Purchase memory first = buy(token, buyer, 1 ether);
        Purchase memory second = buy(token, stranger, 0.5 ether);
        uint256 sale = sellAll(token, buyer);
        uint256 spent = first.spent + second.spent;
        uint256 minimum = spent / 101 + sale / 100;
        uint256 maximum = spent / 100 + sale / 99;
        uint256 creatorBefore = creator.balance;
        uint256 strangerBefore = stranger.balance;
        vm.prank(stranger);
        try pad.claimFees(token) {} catch {}
        assertEq(stranger.balance, strangerBefore, "stranger gets no creator fees");
        vm.prank(creator);
        try pad.claimFees(token) {} catch {}
        uint256 paid = creator.balance - creatorBefore;
        assertGe(paid + 4, minimum, "creator earns at least 1% on top of net trades");
        assertLe(paid, maximum + 4, "creator earns at most 1% of gross trades");
    }

    function test_everyoneCanSellBack() public {
        address token = create();
        address third = makeAddr("third buyer");
        vm.deal(third, 10 ether);
        buy(token, buyer, 0.3 ether);
        buy(token, stranger, 0.6 ether);
        buy(token, third, 1.1 ether);
        sellAll(token, stranger);
        sellAll(token, buyer);
        sellAll(token, third);
    }

    function test_curvesAreSeparate() public {
        address first = create();
        address second = create();
        uint256 snapshot = vm.snapshotState();
        Purchase memory baseline = buy(second, buyer, 0.5 ether);
        vm.revertToState(snapshot);
        fill(first);
        vm.prank(stranger);
        try pad.graduate(second) {} catch {}
        (uint256 ethReserve,) = reserves(second);
        assertEq(ethReserve, 0, "an unfunded curve cannot graduate");
        Purchase memory afterOtherTrades = buy(second, buyer, 0.5 ether);
        assertEq(afterOtherTrades.spent, baseline.spent, "other curve changes no payment");
        assertEq(afterOtherTrades.received, baseline.received, "other curve changes no price");
    }
}
