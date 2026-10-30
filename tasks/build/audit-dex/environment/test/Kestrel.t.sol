// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {Test} from "forge-std/Test.sol";
import {KestrelVault} from "../src/KestrelVault.sol";
import {KestrelRouter} from "../src/KestrelRouter.sol";
import {IKestrelVault} from "../src/interfaces/IKestrelVault.sol";
import {MockERC20} from "./mocks/MockERC20.sol";

contract KestrelTest is Test {
    KestrelVault vault;
    KestrelRouter router;
    MockERC20 weth;
    MockERC20 usdc;
    MockERC20 dai;

    address admin = makeAddr("admin");
    address treasury = makeAddr("treasury");
    address alice = makeAddr("alice");
    address bob = makeAddr("bob");

    uint16 constant FEE = 30;

    function setUp() public {
        vault = new KestrelVault(admin, treasury, 2000);
        router = new KestrelRouter(vault);
        weth = new MockERC20("Wrapped Ether", "WETH", 18);
        usdc = new MockERC20("USD Coin", "USDC", 6);
        dai = new MockERC20("Dai", "DAI", 18);

        address[2] memory users = [alice, bob];
        for (uint256 i; i < users.length; ++i) {
            weth.mint(users[i], 1_000e18);
            usdc.mint(users[i], 4_000_000e6);
            dai.mint(users[i], 4_000_000e18);
            vm.startPrank(users[i]);
            weth.approve(address(router), type(uint256).max);
            usdc.approve(address(router), type(uint256).max);
            dai.approve(address(router), type(uint256).max);
            vm.stopPrank();
        }
    }

    function _seed() internal {
        vm.startPrank(alice);
        router.addLiquidity(address(weth), address(usdc), FEE, 100e18, 300_000e6, 0, 0, alice, block.timestamp);
        router.addLiquidity(address(usdc), address(dai), 5, 1_000_000e6, 1_000_000e18, 0, 0, alice, block.timestamp);
        vm.stopPrank();
    }

    function _pool(address a, address b, uint16 fee) internal view returns (bytes32) {
        (address t0, address t1) = a < b ? (a, b) : (b, a);
        return vault.computePoolId(t0, t1, fee);
    }

    function _path(address a, address b) internal pure returns (address[] memory p) {
        p = new address[](2);
        p[0] = a;
        p[1] = b;
    }

    function _fees(uint16 f) internal pure returns (uint16[] memory f_) {
        f_ = new uint16[](1);
        f_[0] = f;
    }

    function test_firstDepositCreatesPoolAndLocksMinimum() public {
        _seed();
        bytes32 id = _pool(address(weth), address(usdc), FEE);
        IKestrelVault.Pool memory pool = vault.getPool(id);
        assertTrue(vault.poolExists(id));
        assertEq(pool.feeBps, FEE);
        assertEq(vault.sharesOf(id, address(0)), vault.MINIMUM_LIQUIDITY());
        assertEq(vault.sharesOf(id, alice) + vault.MINIMUM_LIQUIDITY(), pool.totalShares);
        assertEq(weth.balanceOf(address(vault)), 100e18);
    }

    function test_secondDepositKeepsRatio() public {
        _seed();
        bytes32 id = _pool(address(weth), address(usdc), FEE);
        uint256 supplyBefore = vault.getPool(id).totalShares;

        vm.prank(bob);
        (uint256 a, uint256 b, uint256 shares) =
            router.addLiquidity(address(weth), address(usdc), FEE, 10e18, 50_000e6, 0, 0, bob, block.timestamp);

        assertEq(a, 10e18);
        assertEq(b, 30_000e6);
        assertEq(shares, supplyBefore / 10);
    }

    function test_swapPaysOutAtQuoteAndAccruesProtocolFee() public {
        _seed();
        uint256 quoted = router.quoteExactIn(1e18, _path(address(weth), address(usdc)), _fees(FEE));

        vm.prank(bob);
        uint256 out = router.swapExactTokensForTokens(
            1e18, quoted, _path(address(weth), address(usdc)), _fees(FEE), bob, block.timestamp
        );

        assertEq(out, quoted);
        assertEq(usdc.balanceOf(bob), 4_000_000e6 + out);
        assertEq(vault.protocolFees(address(weth)), 1e18 * 30 / 10_000 * 2000 / 10_000);
    }

    function test_multiHopSwap() public {
        _seed();
        address[] memory path = new address[](3);
        path[0] = address(weth);
        path[1] = address(usdc);
        path[2] = address(dai);
        uint16[] memory fees = new uint16[](2);
        fees[0] = FEE;
        fees[1] = 5;
        uint256 quoted = router.quoteExactIn(2e18, path, fees);

        vm.prank(bob);
        uint256 out = router.swapExactTokensForTokens(2e18, quoted, path, fees, bob, block.timestamp);

        assertEq(out, quoted);
        assertEq(dai.balanceOf(bob), 4_000_000e18 + out);
        assertEq(usdc.balanceOf(address(router)), 0);
    }

    function test_swapRevertsBelowMinimumOut() public {
        _seed();
        uint256 quoted = router.quoteExactIn(1e18, _path(address(weth), address(usdc)), _fees(FEE));
        vm.prank(bob);
        vm.expectRevert(KestrelRouter.InsufficientOutputAmount.selector);
        router.swapExactTokensForTokens(1e18, quoted + 1, _path(address(weth), address(usdc)), _fees(FEE), bob, block.timestamp);
    }

    function test_expiredDeadlineReverts() public {
        _seed();
        vm.warp(1000);
        vm.prank(bob);
        vm.expectRevert(KestrelRouter.Expired.selector);
        router.swapExactTokensForTokens(1e18, 0, _path(address(weth), address(usdc)), _fees(FEE), bob, 999);
    }

    function test_removeLiquidityThroughRouter() public {
        _seed();
        bytes32 id = _pool(address(weth), address(usdc), FEE);
        uint256 shares = vault.sharesOf(id, alice);

        vm.startPrank(alice);
        vault.setOperator(address(router), true);
        (uint256 a, uint256 b) =
            router.removeLiquidity(address(weth), address(usdc), FEE, shares / 2, 0, 0, alice, block.timestamp);
        vm.stopPrank();

        assertApproxEqRel(a, 50e18, 1e12);
        assertApproxEqRel(b, 150_000e6, 1e12);
        assertEq(vault.sharesOf(id, alice), shares - shares / 2);
    }

    function test_removeLiquidityNeedsOperatorApproval() public {
        _seed();
        vm.prank(alice);
        vm.expectRevert(IKestrelVault.Unauthorized.selector);
        router.removeLiquidity(address(weth), address(usdc), FEE, 1e18, 0, 0, alice, block.timestamp);
    }

    function test_liquidityProvidersEarnSwapFees() public {
        _seed();
        bytes32 id = _pool(address(weth), address(usdc), FEE);
        IKestrelVault.Pool memory before = vault.getPool(id);

        vm.startPrank(bob);
        uint256 usdcOut = router.swapExactTokensForTokens(
            10e18, 0, _path(address(weth), address(usdc)), _fees(FEE), bob, block.timestamp
        );
        router.swapExactTokensForTokens(usdcOut, 0, _path(address(usdc), address(weth)), _fees(FEE), bob, block.timestamp);
        vm.stopPrank();

        IKestrelVault.Pool memory afterSwaps = vault.getPool(id);
        assertGt(afterSwaps.reserve0 * afterSwaps.reserve1, before.reserve0 * before.reserve1);
    }

    function test_skimReturnsStrayTokens() public {
        _seed();
        vm.prank(bob);
        assertTrue(weth.transfer(address(vault), 1e18));
        uint256 skimmed = vault.skim(address(weth), bob);
        assertEq(skimmed, 1e18);
        assertEq(weth.balanceOf(bob), 1_000e18);
    }

    function test_collectSendsFeesToTreasury() public {
        _seed();
        vm.prank(bob);
        router.swapExactTokensForTokens(5e18, 0, _path(address(weth), address(usdc)), _fees(FEE), bob, block.timestamp);
        uint256 accrued = vault.protocolFees(address(weth));
        assertGt(accrued, 0);

        address[] memory tokens = new address[](1);
        tokens[0] = address(weth);
        vault.collectProtocolFees(tokens);

        assertEq(weth.balanceOf(treasury), accrued);
        assertEq(vault.protocolFees(address(weth)), 0);
    }

    function test_adminControls() public {
        vm.expectRevert(IKestrelVault.Unauthorized.selector);
        vault.setProtocolShare(100);

        vm.startPrank(admin);
        vm.expectRevert(IKestrelVault.ProtocolShareTooHigh.selector);
        vault.setProtocolShare(2501);
        vault.setProtocolShare(1000);
        vault.setFeeTier(50, true);
        vault.transferOwnership(bob);
        vm.stopPrank();

        vm.prank(bob);
        vault.acceptOwnership();
        assertEq(vault.owner(), bob);
        assertEq(vault.protocolShareBps(), 1000);
        assertTrue(vault.feeTierEnabled(50));
    }

    function test_createPoolRejectsDisabledTierAndDuplicates() public {
        vm.expectRevert(IKestrelVault.FeeTierDisabled.selector);
        vault.createPool(address(weth), address(usdc), 25);

        vault.createPool(address(weth), address(usdc), FEE);
        vm.expectRevert(IKestrelVault.PoolExists.selector);
        vault.createPool(address(usdc), address(weth), FEE);
    }
}
