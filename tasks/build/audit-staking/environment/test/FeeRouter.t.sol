// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {BaseTest} from "./Base.t.sol";
import {FeeRouter} from "../src/FeeRouter.sol";

contract FeeRouterTest is BaseTest {
    function test_splitsFees() public {
        _stake(alice, 100e18);
        _collectFees(50e18);
        assertEq(blst.balanceOf(treasury), 10e18);
        assertEq(staking.unvestedRewards(), staking.rewardRate() * 7 days);
        assertApproxEqAbs(staking.unvestedRewards(), 40e18, 1e6);
    }

    function test_emptyDistributeIsNoop() public {
        (uint256 toStakers, uint256 toTreasury) = router.distribute();
        assertEq(toStakers + toTreasury, 0);
    }

    function test_stakerShareBounds() public {
        vm.startPrank(governance);
        vm.expectRevert(FeeRouter.InvalidBps.selector);
        router.setStakerBps(4_999);
        router.setStakerBps(10_000);
        vm.stopPrank();

        _stake(alice, 100e18);
        _collectFees(10e18);
        assertEq(blst.balanceOf(treasury), 0);
    }
}
