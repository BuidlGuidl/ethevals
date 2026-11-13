// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {Test} from "forge-std/Test.sol";
import {IERC20} from "../src/interfaces/IERC20.sol";
import {BallastStaking} from "../src/BallastStaking.sol";
import {ShortfallModule} from "../src/ShortfallModule.sol";
import {FeeRouter} from "../src/FeeRouter.sol";
import {MockBLST} from "./mocks/MockBLST.sol";

abstract contract BaseTest is Test {
    MockBLST internal blst;
    BallastStaking internal staking;
    ShortfallModule internal shortfall;
    FeeRouter internal router;

    address internal governance = makeAddr("governance");
    address internal guardian = makeAddr("guardian");
    address internal treasury = makeAddr("treasury");
    address internal market = makeAddr("market");
    address internal alice = makeAddr("alice");
    address internal bob = makeAddr("bob");

    function setUp() public virtual {
        blst = new MockBLST();
        staking = new BallastStaking(IERC20(address(blst)), governance);
        shortfall = new ShortfallModule(staking, governance, guardian);
        router = new FeeRouter(IERC20(address(blst)), staking, treasury, governance);
        vm.prank(governance);
        staking.setSlasher(address(shortfall));

        _fund(alice, 1_000e18);
        _fund(bob, 1_000e18);
    }

    function _fund(address who, uint256 amount) internal {
        blst.mint(who, amount);
        vm.prank(who);
        blst.approve(address(staking), type(uint256).max);
    }

    function _stake(address who, uint256 amount) internal returns (uint256) {
        vm.prank(who);
        return staking.stake(amount, who);
    }

    function _collectFees(uint256 amount) internal {
        blst.mint(address(router), amount);
        router.distribute();
    }
}
