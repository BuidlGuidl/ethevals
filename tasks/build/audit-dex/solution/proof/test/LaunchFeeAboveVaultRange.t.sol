// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {console} from "forge-std/Test.sol";
import {ProofBase} from "./ProofBase.sol";

/// KestrelLaunchFee starts a launch pool at up to 50%, but KestrelVault.swapFee treats any module
/// answer of 10% or more as invalid and charges the 1% tier fee instead. So in the first part of the
/// decay, when the launch fee is highest, a sniper pays 1%.
contract LaunchFeeAboveVaultRangeTest is ProofBase {
    function test_sniperPaysTierFeeWhileLaunchFeeIsAboveTenPercent() public {
        // The team creates and seeds the launch pool in one transaction, as the README says.
        vm.prank(team);
        router.addLiquidity(address(meme), address(weth), LAUNCH_TIER, 100_000_000e18, 100e18, 0, 0, team, block.timestamp);
        bytes32 id = _pool(address(meme), address(weth), LAUNCH_TIER);

        skip(1 minutes);
        uint256 intendedFee = launchFee.swapFee(id);
        console.log("launch fee the module sets (bps)", intendedFee);
        console.log("fee the vault charges (bps)", vault.swapFee(id));
        assertGt(intendedFee, 2900);
        assertEq(vault.swapFee(id), LAUNCH_TIER);

        uint256 buy = 20e18;
        uint256 intendedOut = _outAt(id, address(weth), buy, intendedFee);
        uint256 tierOut = _outAt(id, address(weth), buy, LAUNCH_TIER);
        vm.prank(trader);
        uint256 out = router.swapExactTokensForTokens(buy, 0, _path(address(weth), address(meme)), _fees(LAUNCH_TIER), trader, block.timestamp);

        console.log("MEME the sniper got", out / 1e18);
        console.log("MEME at the launch fee", intendedOut / 1e18);
        assertEq(out, tierOut);
        assertGt(out, intendedOut * 125 / 100);

        // Once the decay brings the module under 10%, the vault does follow it: the gap is only the
        // high part of the launch fee.
        skip(45 minutes);
        assertEq(vault.swapFee(id), launchFee.swapFee(id));
        assertGt(vault.swapFee(id), LAUNCH_TIER);
    }
}
