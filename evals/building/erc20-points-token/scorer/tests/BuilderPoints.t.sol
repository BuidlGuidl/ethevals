// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {Test} from "forge-std/Test.sol";
import {IERC20} from "forge-std/interfaces/IERC20.sol";
import {BuilderPoints} from "workspace/src/BuilderPoints.sol";

contract BuilderPointsTest is Test {
    uint256 constant UNIT = 10 ** 6;
    uint256 constant INITIAL = 100_000 * UNIT;
    uint256 constant CAP = 1_000_000 * UNIT;

    BuilderPoints points;
    IERC20 token;
    address alice = makeAddr("alice");
    address bob = makeAddr("bob");

    function setUp() public {
        points = new BuilderPoints();
        token = IERC20(address(points));
    }

    function test_decimals_match_usdc() public view {
        assertEq(token.decimals(), 6, "decimals");
    }

    function test_name_and_symbol() public view {
        assertEq(token.name(), "Builder Points", "name");
        assertEq(token.symbol(), "BPT", "symbol");
    }

    function test_deployer_holds_initial_supply() public view {
        assertEq(token.totalSupply(), INITIAL, "total supply");
        assertEq(token.balanceOf(address(this)), INITIAL, "deployer balance");
    }

    function test_deployer_can_mint() public {
        points.mint(alice, 5 * UNIT);
        assertEq(token.balanceOf(alice), 5 * UNIT, "alice balance after mint");
        assertEq(token.totalSupply(), INITIAL + 5 * UNIT, "total supply after mint");
    }

    function test_non_deployer_mint_reverts() public {
        vm.prank(alice);
        vm.expectRevert();
        points.mint(alice, 1);
    }

    function test_cap_is_one_million() public {
        points.mint(alice, CAP - INITIAL);
        assertEq(token.totalSupply(), CAP, "total supply at the cap");
        vm.expectRevert();
        points.mint(alice, 1);
    }

    function test_holders_can_transfer() public {
        assertTrue(token.transfer(alice, 5 * UNIT), "transfer returns true");
        vm.prank(alice);
        assertTrue(token.transfer(bob, 2 * UNIT), "holder transfer returns true");
        assertEq(token.balanceOf(alice), 3 * UNIT, "alice balance");
        assertEq(token.balanceOf(bob), 2 * UNIT, "bob balance");
    }

    function test_transfer_over_balance_reverts() public {
        vm.prank(alice);
        vm.expectRevert();
        token.transfer(bob, 1);
    }

    function test_approve_and_transfer_from() public {
        assertTrue(token.approve(alice, 3 * UNIT), "approve returns true");
        assertEq(token.allowance(address(this), alice), 3 * UNIT, "allowance");
        vm.prank(alice);
        assertTrue(token.transferFrom(address(this), bob, 3 * UNIT), "transferFrom returns true");
        assertEq(token.balanceOf(bob), 3 * UNIT, "bob balance");
        assertEq(token.allowance(address(this), alice), 0, "allowance spent");
    }

    function test_transfer_from_without_allowance_reverts() public {
        vm.prank(alice);
        vm.expectRevert();
        token.transferFrom(address(this), bob, 1);
    }
}
