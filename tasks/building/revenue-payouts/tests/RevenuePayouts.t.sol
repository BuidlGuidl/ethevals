// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {Test} from "forge-std/Test.sol";
import {RevenuePayouts} from "../workspace/src/RevenuePayouts.sol";

interface IRevenuePayoutsRelease {
    function release(address payee) external;
}

interface IRevenuePayouts is IRevenuePayoutsRelease {
    function release(address token, address payee) external;
}

// A payee that refuses plain ETH, like a contract with no receive function.
contract RejectingPayee {
    receive() external payable {
        revert("no ETH");
    }
}

// A payee whose receive costs more than 2,300 gas, like a smart wallet that records deposits.
contract GasHungryPayee {
    uint256 public received;
    receive() external payable {
        received += msg.value;
    }
}

// A payee that asks to be paid again from inside the payment.
contract ReentrantPayee {
    IRevenuePayoutsRelease public payouts;
    uint256 public calls;
    function setRevenuePayouts(IRevenuePayoutsRelease s) external {
        payouts = s;
    }
    receive() external payable {
        if (gasleft() > 2300 && calls++ == 0) {
            try payouts.release(address(this)) {} catch {}
        }
    }
}

contract TokenBalances {
    mapping(address => uint256) public balanceOf;
    mapping(address => bool) public frozen;

    function mint(address to, uint256 amount) external {
        balanceOf[to] += amount;
    }

    function freeze(address account) external {
        frozen[account] = true;
    }

    function move(address to, uint256 amount) internal {
        balanceOf[msg.sender] -= amount;
        balanceOf[to] += amount;
    }
}

contract MockUSDC is TokenBalances {
    function transfer(address to, uint256 amount) external returns (bool) {
        require(!frozen[msg.sender] && !frozen[to], "frozen");
        move(to, amount);
        return true;
    }
}

contract MockUSDT is TokenBalances {
    function transfer(address to, uint256 amount) external {
        require(!frozen[msg.sender], "frozen");
        move(to, amount);
    }
}

contract RevenuePayoutsTest is Test {
    address constant A = address(0xA11CE);
    address constant B = address(0xB0B);
    address constant C = address(0xCA11);
    address constant STRANGER = address(0xD00D);
    MockUSDC constant USDC = MockUSDC(0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48);
    MockUSDT constant USDT = MockUSDT(0xdAC17F958D2ee523a2206206994597C13D831ec7);

    function setUp() public {
        vm.deal(address(this), 10 ether);
        vm.etch(address(USDC), address(new MockUSDC()).code);
        vm.etch(address(USDT), address(new MockUSDT()).code);
        USDC.mint(address(this), 2_000_000);
        USDT.mint(address(this), 2_000_000);
    }

    function lists(address first) internal pure returns (address[] memory payees, uint256[] memory shares) {
        payees = new address[](3);
        payees[0] = first;
        payees[1] = B;
        payees[2] = C;
        shares = new uint256[](3);
        shares[0] = 50;
        shares[1] = 30;
        shares[2] = 20;
    }

    function create(address first) internal returns (IRevenuePayouts) {
        (address[] memory payees, uint256[] memory shares) = lists(first);
        return IRevenuePayouts(address(new RevenuePayouts(payees, shares)));
    }

    function sendETH(IRevenuePayouts payouts, uint256 amount) internal {
        (bool ok,) = address(payouts).call{value: amount}("");
        assertTrue(ok, "plain ETH transfer failed");
    }

    function test_laterETH() public {
        IRevenuePayouts payouts = create(A);
        sendETH(payouts, 1 ether);
        vm.prank(A);
        payouts.release(A);
        assertEq(A.balance, 0.5 ether);
        sendETH(payouts, 1 ether);
        vm.prank(A);
        payouts.release(A);
        vm.prank(B);
        try payouts.release(B) {} catch {}
        vm.prank(C);
        try payouts.release(C) {} catch {}
        assertEq(A.balance, 1 ether);
        assertEq(B.balance, 0.6 ether);
        assertEq(C.balance, 0.4 ether);
        assertEq(address(payouts).balance, 0);
    }

    function test_noDoublePayment() public {
        IRevenuePayouts payouts = create(A);
        sendETH(payouts, 1 ether);
        vm.prank(A);
        payouts.release(A);
        assertEq(A.balance, 0.5 ether);
        vm.prank(A);
        try payouts.release(A) {} catch {}
        assertEq(A.balance, 0.5 ether);
    }

    function test_rounding() public {
        (address[] memory payees, uint256[] memory shares) = lists(A);
        shares[0] = 33;
        shares[1] = 33;
        shares[2] = 34;
        uint256[3] memory expected = [uint256(33), 33, 34];
        // First claims isolate rounding from the released ledger.
        for (uint256 i; i < payees.length; ++i) {
            IRevenuePayouts payouts = IRevenuePayouts(address(new RevenuePayouts(payees, shares)));
            sendETH(payouts, 101);
            uint256 before = payees[i].balance;
            vm.prank(payees[i]);
            payouts.release(payees[i]);
            assertEq(payees[i].balance - before, expected[i]);
        }
    }

    function test_gasHungryPayee() public {
        GasHungryPayee payee = new GasHungryPayee();
        IRevenuePayouts payouts = create(address(payee));
        sendETH(payouts, 1 ether);
        vm.prank(address(payee));
        payouts.release(address(payee));
        assertEq(address(payee).balance, 0.5 ether);
        assertEq(payee.received(), 0.5 ether);
    }

    function test_rejectingPayee() public {
        RejectingPayee payee = new RejectingPayee();
        IRevenuePayouts payouts = create(address(payee));
        sendETH(payouts, 1 ether);
        vm.prank(address(payee));
        try payouts.release(address(payee)) {} catch {}
        vm.prank(B);
        payouts.release(B);
        assertEq(address(payee).balance, 0);
        assertEq(B.balance, 0.3 ether);
    }

    function test_reentrantPayee() public {
        ReentrantPayee payee = new ReentrantPayee();
        IRevenuePayouts payouts = create(address(payee));
        payee.setRevenuePayouts(payouts);
        sendETH(payouts, 1 ether);
        vm.prank(address(payee));
        payouts.release(address(payee));
        assertEq(address(payee).balance, 0.5 ether);
    }

    function test_strangerRelease() public {
        IRevenuePayouts payouts = create(A);
        sendETH(payouts, 1 ether);
        vm.prank(STRANGER);
        payouts.release(B);
        assertEq(B.balance, 0.3 ether);
        assertEq(STRANGER.balance, 0);
    }

    function test_constructorValidation() public {
        (address[] memory payees, uint256[] memory shares) = lists(A);
        uint256[] memory shortShares = new uint256[](1);
        shortShares[0] = 1;
        vm.expectRevert();
        new RevenuePayouts(payees, shortShares);
        shares[1] = 0;
        vm.expectRevert();
        new RevenuePayouts(payees, shares);
        shares[1] = 30;
        payees[1] = address(0);
        vm.expectRevert();
        new RevenuePayouts(payees, shares);
    }

    function test_usdtNoReturn() public {
        IRevenuePayouts payouts = create(A);
        USDT.transfer(address(payouts), 1_000_000);
        payouts.release(address(USDT), A);
        assertEq(USDT.balanceOf(A), 500_000);
    }

    function test_laterTokens() public {
        IRevenuePayouts payouts = create(A);
        USDC.transfer(address(payouts), 1_000_000);
        payouts.release(address(USDC), A);
        assertEq(USDC.balanceOf(A), 500_000);
        USDC.transfer(address(payouts), 1_000_000);
        payouts.release(address(USDC), A);
        try payouts.release(address(USDC), B) {} catch {}
        try payouts.release(address(USDC), C) {} catch {}
        assertEq(USDC.balanceOf(A), 1_000_000);
        assertEq(USDC.balanceOf(B), 600_000);
        assertEq(USDC.balanceOf(C), 400_000);
        assertEq(USDC.balanceOf(address(payouts)), 0);
    }

    function test_frozenUSDCPayee() public {
        IRevenuePayouts payouts = create(A);
        USDC.transfer(address(payouts), 1_000_000);
        USDC.freeze(A);
        vm.expectRevert();
        payouts.release(address(USDC), A);
        payouts.release(address(USDC), B);
        assertEq(USDC.balanceOf(A), 0);
        assertEq(USDC.balanceOf(B), 300_000);
    }

    function test_assetLedgers() public {
        IRevenuePayouts payouts = create(A);
        sendETH(payouts, 1 ether);
        USDC.transfer(address(payouts), 1_000_000);
        payouts.release(address(USDC), A);
        vm.prank(A);
        payouts.release(A);
        assertEq(USDC.balanceOf(A), 500_000);
        assertEq(A.balance, 0.5 ether);
    }
}
