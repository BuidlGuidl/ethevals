// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {Test, console} from "forge-std/Test.sol";
import {KestrelVault} from "kestrel/src/KestrelVault.sol";
import {KestrelRouter} from "kestrel/src/KestrelRouter.sol";
import {IKestrelVault} from "kestrel/src/interfaces/IKestrelVault.sol";
import {MockERC20} from "kestrel/test/mocks/MockERC20.sol";

/// collectProtocolFees sends fees out but leaves them in trackedBalance, so the next caller who
/// delivers that token is credited with what it sent minus the collected fees.
contract CollectedFeesStayTrackedTest is Test {
    KestrelVault vault;
    KestrelRouter router;
    MockERC20 weth;
    MockERC20 usdc;

    address admin = makeAddr("admin");
    address treasury = makeAddr("treasury");
    address lp = makeAddr("lp");
    address trader = makeAddr("trader");
    address victim = makeAddr("victim");
    address keeper = makeAddr("keeper");

    uint16 constant FEE = 30;
    uint256 collected;

    function setUp() public {
        vault = new KestrelVault(admin, treasury, 2000);
        router = new KestrelRouter(vault);
        weth = new MockERC20("Wrapped Ether", "WETH", 18);
        usdc = new MockERC20("USD Coin", "USDC", 6);

        address[3] memory users = [lp, trader, victim];
        for (uint256 i; i < users.length; ++i) {
            weth.mint(users[i], 10_000e18);
            usdc.mint(users[i], 30_000_000e6);
            vm.startPrank(users[i]);
            weth.approve(address(router), type(uint256).max);
            usdc.approve(address(router), type(uint256).max);
            vm.stopPrank();
        }

        vm.prank(lp);
        router.addLiquidity(address(weth), address(usdc), FEE, 1_000e18, 3_000_000e6, 0, 0, lp, block.timestamp);

        // Ordinary trading accrues protocol fees in WETH.
        vm.startPrank(trader);
        for (uint256 i; i < 10; ++i) {
            uint256 out = router.swapExactTokensForTokens(100e18, 0, _path(address(weth), address(usdc)), _fees(), trader, block.timestamp);
            router.swapExactTokensForTokens(out, 0, _path(address(usdc), address(weth)), _fees(), trader, block.timestamp);
        }
        vm.stopPrank();

        collected = vault.protocolFees(address(weth));
        address[] memory tokens = new address[](1);
        tokens[0] = address(weth);
        vm.prank(keeper);
        vault.collectProtocolFees(tokens);
        assertEq(weth.balanceOf(treasury), collected);
    }

    function test_collectionLeavesFeesInTrackedBalance() public view {
        console.log("collected WETH fees (wei)", collected);
        assertGt(collected, 0.5e18);
        assertEq(vault.trackedBalance(address(weth)) - weth.balanceOf(address(vault)), collected);
    }

    function test_nextSwapperIsShortCreditedByCollectedFees() public {
        uint256 amountIn = 200e18;
        uint256 quoted = router.quoteExactIn(amountIn, _path(address(weth), address(usdc)), _fees());
        uint256 creditedQuote = router.quoteExactIn(amountIn - collected, _path(address(weth), address(usdc)), _fees());

        uint256 before = weth.balanceOf(victim);
        vm.prank(victim);
        // 1% slippage tolerance does not catch it.
        uint256 out = router.swapExactTokensForTokens(
            amountIn, quoted * 99 / 100, _path(address(weth), address(usdc)), _fees(), victim, block.timestamp
        );

        assertEq(before - weth.balanceOf(victim), amountIn);
        assertEq(out, creditedQuote);
        assertLt(out, quoted);
        // The vault is consistent again only because the victim covered the collected fees.
        assertEq(vault.trackedBalance(address(weth)), weth.balanceOf(address(vault)));
    }

    function test_nextLiquidityProviderIsShortCredited() public {
        bytes32 id = vault.computePoolId(address(weth) < address(usdc) ? address(weth) : address(usdc), address(weth) < address(usdc) ? address(usdc) : address(weth), FEE);
        IKestrelVault.Pool memory pool = vault.getPool(id);
        (uint256 rWeth, uint256 rUsdc) = address(weth) == pool.token0 ? (pool.reserve0, pool.reserve1) : (pool.reserve1, pool.reserve0);

        vm.prank(victim);
        (uint256 wethSent,, uint256 shares) =
            router.addLiquidity(address(weth), address(usdc), FEE, 100e18, type(uint128).max, 0, 0, victim, block.timestamp);

        uint256 fairShares = wethSent * pool.totalShares / rWeth;
        uint256 creditedShares = (wethSent - collected) * pool.totalShares / rWeth;
        assertEq(shares, creditedShares);
        assertLt(shares, fairShares);
        assertGt(rUsdc, 0);
    }

    function test_smallDepositsRevertUntilTheGapIsCovered() public {
        vm.prank(victim);
        vm.expectRevert(); // arithmetic underflow in _settle
        router.swapExactTokensForTokens(collected / 2, 0, _path(address(weth), address(usdc)), _fees(), victim, block.timestamp);
    }

    function _path(address a, address b) internal pure returns (address[] memory p) {
        p = new address[](2);
        p[0] = a;
        p[1] = b;
    }

    function _fees() internal pure returns (uint16[] memory f) {
        f = new uint16[](1);
        f[0] = FEE;
    }
}
