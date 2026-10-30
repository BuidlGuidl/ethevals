// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {Test} from "forge-std/Test.sol";
import {SluiceVault} from "../src/SluiceVault.sol";
import {LendingMarketStrategy} from "../src/strategies/LendingMarketStrategy.sol";
import {IERC4626} from "../src/interfaces/IERC4626.sol";
import {MockERC20} from "./mocks/MockERC20.sol";
import {MockLendingMarket} from "./mocks/MockLendingMarket.sol";

/// Copy into the audited project's test/ folder and run: forge test --match-contract ProofTest
contract ProofTest is Test {
    address internal owner = makeAddr("owner");
    address internal allocator = makeAddr("allocator");
    address internal treasury = makeAddr("treasury");
    address internal alice = makeAddr("alice");
    address internal bob = makeAddr("bob");

    MockERC20 internal usdc;
    MockLendingMarket internal market;
    SluiceVault internal vault;
    LendingMarketStrategy internal strategy;

    function setUp() public {
        usdc = new MockERC20("USD Coin", "USDC", 6);
        market = new MockLendingMarket(usdc);
        vault = new SluiceVault(usdc, "Sluice USDC", "slUSDC", owner, treasury, 0, 1_500, 0);
        strategy = new LendingMarketStrategy(address(vault), IERC4626(address(market)));
        vm.startPrank(owner);
        vault.setIsAllocator(allocator, true);
        vault.submitStrategy(strategy, type(uint256).max);
        vault.acceptStrategy(strategy);
        vm.stopPrank();
        for (uint256 i; i < 2; ++i) {
            address account = i == 0 ? alice : bob;
            usdc.mint(account, 1_000_000e6);
            vm.prank(account);
            usdc.approve(address(vault), type(uint256).max);
        }
    }

    /// High 1: a withdrawal that pulls from a strategy lowers its assets but not `deployedAssets`,
    /// so the next harvest reads the withdrawal as a loss and the treasury's fee on real profit is lost.
    function test_withdrawalErasesPerformanceFee() public {
        vm.prank(alice);
        vault.deposit(1_000_000e6, alice);
        vm.prank(allocator);
        vault.allocate(strategy, 1_000_000e6);

        market.accrueInterest(50_000e6); // 50,000 USDC of real profit, 7,500 owed to the treasury

        vm.prank(alice);
        vault.withdraw(200_000e6, alice, alice); // idle is empty, so this undeploys from the strategy
        assertEq(strategy.deployedAssets(), 1_000_000e6, "baseline still counts the withdrawn 200,000");

        vm.prank(allocator);
        vault.harvest(strategy);

        assertEq(vault.accruedFees(), 0, "no fee booked on 50,000 of profit");
        assertApproxEqAbs(strategy.deployedAssets(), 850_000e6, 1, "profit absorbed into the new baseline");
    }

    /// High 2: fees booked at harvest stay in the vault's balance and `totalAssets` still counts them,
    /// so a depositor who redeems before `claimFees` takes part of the fee, and the claim then comes
    /// out of the depositors who stayed.
    function test_unclaimedFeesInflateSharePrice() public {
        vm.prank(alice);
        uint256 aliceShares = vault.deposit(500_000e6, alice);
        vm.prank(bob);
        uint256 bobShares = vault.deposit(500_000e6, bob);
        vm.prank(allocator);
        vault.allocate(strategy, 1_000_000e6);

        market.accrueInterest(100_000e6);
        vm.prank(allocator);
        vault.harvest(strategy);
        uint256 fee = vault.accruedFees();
        assertApproxEqAbs(fee, 15_000e6, 1);

        // Each holder's fair share: half of (1,100,000 - 15,000 fee) = 542,500.
        uint256 fair = 542_500e6;
        assertApproxEqAbs(vault.totalAssets(), 1_100_000e6, 2, "fee owed to treasury still counted");

        vm.prank(alice);
        uint256 aliceOut = vault.redeem(aliceShares, alice, alice);
        assertGt(aliceOut, fair + 7_000e6, "alice exits with about 550,000");

        vault.claimFees();
        assertApproxEqAbs(usdc.balanceOf(treasury), 15_000e6, 1);

        uint256 bobValue = vault.previewRedeem(bobShares);
        assertLt(bobValue, fair - 7_000e6, "bob is left with about 535,000");
    }
}
