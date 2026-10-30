// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {BaseTest} from "./Base.t.sol";
import {BallastStaking} from "../src/BallastStaking.sol";
import {ShortfallModule} from "../src/ShortfallModule.sol";

contract ShortfallModuleTest is BaseTest {
    function setUp() public override {
        super.setUp();
        _stake(alice, 100e18);
        _stake(bob, 300e18);
    }

    function _propose(uint256 assets) internal returns (uint256) {
        vm.prank(governance);
        return shortfall.proposeSlash(assets, market, "bad debt");
    }

    function test_slashSharedByStakers() public {
        uint256 id = _propose(40e18);
        vm.warp(block.timestamp + 2 days);
        shortfall.executeSlash(id);

        assertEq(blst.balanceOf(market), 40e18);
        assertEq(staking.balanceOf(alice), 90e18);
        assertEq(staking.balanceOf(bob), 270e18);
    }

    function test_slashCappedAtMax() public {
        uint256 id = _propose(1_000e18);
        vm.warp(block.timestamp + 2 days);
        uint256 slashed = shortfall.executeSlash(id);
        assertEq(slashed, 120e18);
        assertEq(staking.totalAssets(), 280e18);
    }

    function test_cannotExecuteEarlyOrLate() public {
        uint256 id = _propose(10e18);
        vm.expectRevert(ShortfallModule.NotExecutable.selector);
        shortfall.executeSlash(id);

        vm.warp(block.timestamp + 5 days + 1);
        vm.expectRevert(ShortfallModule.NotExecutable.selector);
        shortfall.executeSlash(id);
    }

    function test_guardianVeto() public {
        uint256 id = _propose(10e18);
        vm.prank(guardian);
        shortfall.veto(id);
        vm.warp(block.timestamp + 2 days);
        vm.expectRevert(ShortfallModule.ProposalClosed.selector);
        shortfall.executeSlash(id);
    }

    function test_onlyGovernanceProposes() public {
        vm.prank(alice);
        vm.expectRevert(ShortfallModule.NotGovernance.selector);
        shortfall.proposeSlash(10e18, market, "");
    }

    function test_onlyModuleSlashes() public {
        vm.prank(governance);
        vm.expectRevert(BallastStaking.NotSlasher.selector);
        staking.slash(10e18, market);
    }

    function test_executeOnce() public {
        uint256 id = _propose(10e18);
        vm.warp(block.timestamp + 2 days);
        shortfall.executeSlash(id);
        vm.expectRevert(ShortfallModule.ProposalClosed.selector);
        shortfall.executeSlash(id);
    }
}
