// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {console} from "forge-std/Test.sol";
import {ProofBase} from "./ProofBase.sol";

/// KestrelLaunchFee measures the decay from the pool's createdAt, assuming the pool is created when its
/// token launches. KestrelVault.createPool lets anyone create any pool at an enabled tier, and the router
/// only creates a pool that does not exist yet. Creating the launch pool early runs the clock out before
/// the team adds liquidity, so the launch has no launch fee at all.
contract LaunchClockStartsAtCreationTest is ProofBase {
    function test_precreatedPoolLaunchesWithTierFee() public {
        // The token is deployed; anyone creates its launch pool before the team seeds it.
        vm.prank(attacker);
        vault.createPool(address(meme), address(weth), LAUNCH_TIER);
        bytes32 id = _pool(address(meme), address(weth), LAUNCH_TIER);

        skip(2 hours);
        // The team launches through the router, which finds the pool and only adds liquidity.
        vm.prank(team);
        router.addLiquidity(address(meme), address(weth), LAUNCH_TIER, 100_000_000e18, 100e18, 0, 0, team, block.timestamp);

        // In the launch block, the module itself already answers the tier fee.
        assertEq(launchFee.swapFee(id), LAUNCH_TIER);
        assertEq(vault.swapFee(id), LAUNCH_TIER);

        // Forty-five minutes in, a pool created at launch would still charge about 8%.
        skip(45 minutes);
        uint256 intendedFee = 3000 - uint256(3000 - LAUNCH_TIER) * 45 minutes / 1 hours;
        uint256 buy = 20e18;
        uint256 intendedOut = _outAt(id, address(weth), buy, intendedFee);
        vm.prank(trader);
        uint256 out = router.swapExactTokensForTokens(buy, 0, _path(address(weth), address(meme)), _fees(LAUNCH_TIER), trader, block.timestamp);

        console.log("fee a pool created at launch would charge (bps)", intendedFee);
        console.log("fee charged (bps)", vault.swapFee(id));
        console.log("MEME bought", out / 1e18);
        console.log("MEME at the intended fee", intendedOut / 1e18);
        assertEq(vault.swapFee(id), LAUNCH_TIER);
        assertGt(out, intendedOut * 105 / 100);
    }
}
