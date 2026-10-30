// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {Test} from "forge-std/Test.sol";
import {KestrelVault} from "kestrel/src/KestrelVault.sol";
import {KestrelRouter} from "kestrel/src/KestrelRouter.sol";
import {KestrelLaunchFee} from "kestrel/src/KestrelLaunchFee.sol";
import {KestrelFarm} from "kestrel/src/KestrelFarm.sol";
import {MockERC20} from "kestrel/test/mocks/MockERC20.sol";

/// Deployment as the README describes it: the 1% tier is the launch tier, and the farm is the fee recipient.
abstract contract ProofBase is Test {
    KestrelVault vault;
    KestrelRouter router;
    KestrelLaunchFee launchFee;
    KestrelFarm farm;
    MockERC20 weth;
    MockERC20 usdc;
    MockERC20 meme;

    address admin = makeAddr("admin");
    address team = makeAddr("team");
    address lp = makeAddr("lp");
    address trader = makeAddr("trader");
    address attacker = makeAddr("attacker");

    uint16 constant LAUNCH_TIER = 100;

    function setUp() public virtual {
        vm.warp(1_800_000_000);
        vault = new KestrelVault(admin, admin, 2000);
        router = new KestrelRouter(vault);
        launchFee = new KestrelLaunchFee(vault, admin, 3000, 1 hours);
        farm = new KestrelFarm(vault, admin);
        vm.startPrank(admin);
        vault.setFeeModule(LAUNCH_TIER, address(launchFee));
        vault.setFeeRecipient(address(farm));
        vm.stopPrank();

        weth = new MockERC20("Wrapped Ether", "WETH", 18);
        usdc = new MockERC20("USD Coin", "USDC", 6);
        meme = new MockERC20("Meme", "MEME", 18);

        address[5] memory users = [team, lp, trader, attacker, admin];
        for (uint256 i; i < users.length; ++i) {
            weth.mint(users[i], 100_000e18);
            usdc.mint(users[i], 300_000_000e6);
            meme.mint(users[i], 1_000_000_000e18);
            vm.startPrank(users[i]);
            weth.approve(address(router), type(uint256).max);
            usdc.approve(address(router), type(uint256).max);
            meme.approve(address(router), type(uint256).max);
            weth.approve(address(farm), type(uint256).max);
            vault.setOperator(address(farm), true);
            vm.stopPrank();
        }
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

    /// Output a swap would give at `feeBps`, from the pool's current reserves.
    function _outAt(bytes32 poolId, address tokenIn, uint256 amountIn, uint256 feeBps) internal view returns (uint256) {
        KestrelVault.Pool memory pool = vault.getPool(poolId);
        (uint256 rIn, uint256 rOut) = tokenIn == pool.token0 ? (pool.reserve0, pool.reserve1) : (pool.reserve1, pool.reserve0);
        uint256 inWithFee = amountIn * (10_000 - feeBps);
        return inWithFee * rOut / (rIn * 10_000 + inWithFee);
    }
}
