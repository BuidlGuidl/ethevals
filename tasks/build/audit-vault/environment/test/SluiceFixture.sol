// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {Test} from "forge-std/Test.sol";
import {SluiceVault} from "../src/SluiceVault.sol";
import {LendingMarketStrategy} from "../src/strategies/LendingMarketStrategy.sol";
import {AaveV3Strategy} from "../src/strategies/AaveV3Strategy.sol";
import {IERC4626} from "../src/interfaces/IERC4626.sol";
import {IAToken} from "../src/interfaces/IAavePool.sol";
import {MockERC20} from "./mocks/MockERC20.sol";
import {MockLendingMarket} from "./mocks/MockLendingMarket.sol";
import {MockAavePool} from "./mocks/MockAavePool.sol";
import {MockRewardsController, MockSwapper} from "./mocks/MockRewards.sol";
import {IRewardsController} from "../src/interfaces/IAavePool.sol";

/// @notice Shared deployment: one lending-market strategy and one Aave strategy, both live.
abstract contract SluiceFixture is Test {
    address internal owner = makeAddr("owner");
    address internal curator = makeAddr("curator");
    address internal allocator = makeAddr("allocator");
    address internal guardian = makeAddr("guardian");
    address internal treasury = makeAddr("treasury");
    address internal alice = makeAddr("alice");
    address internal bob = makeAddr("bob");

    MockERC20 internal usdc;
    MockLendingMarket internal marketA;
    MockAavePool internal aave;
    MockRewardsController internal rewards;
    MockSwapper internal swapper;
    MockERC20 internal rewardToken;
    SluiceVault internal vault;
    LendingMarketStrategy internal strategyA;
    AaveV3Strategy internal strategyB;

    function setUp() public virtual {
        usdc = new MockERC20("USD Coin", "USDC", 6);
        marketA = new MockLendingMarket(usdc);
        aave = new MockAavePool(usdc);
        rewards = new MockRewardsController();
        rewardToken = new MockERC20("Reward", "RWD", 18);
        swapper = new MockSwapper(2e6); // 2 USDC per reward token
        vault = new SluiceVault(usdc, "Sluice USDC", "slUSDC", owner, treasury, 0, 1_500, 0);
        strategyA = new LendingMarketStrategy(address(vault), IERC4626(address(marketA)));
        strategyB = new AaveV3Strategy(
            address(vault), IAToken(address(aave.aToken())), IRewardsController(address(rewards))
        );

        vm.startPrank(owner);
        vault.setCurator(curator);
        vault.setIsAllocator(allocator, true);
        vault.submitGuardian(guardian);
        vault.setRewardSwapper(address(swapper));
        vm.stopPrank();

        vm.startPrank(curator);
        vault.submitStrategy(strategyA, 1_000_000e6);
        vault.submitStrategy(strategyB, 1_000_000e6);
        vm.stopPrank();
        vault.acceptStrategy(strategyA);
        vault.acceptStrategy(strategyB);

        vm.prank(owner);
        vault.submitTimelock(1 days);

        _fund(alice, 1_000_000e6);
        _fund(bob, 1_000_000e6);
    }

    function _fund(address account, uint256 amount) internal {
        usdc.mint(account, amount);
        vm.prank(account);
        usdc.approve(address(vault), type(uint256).max);
    }

    function _deposit(address account, uint256 amount) internal returns (uint256) {
        vm.prank(account);
        return vault.deposit(amount, account);
    }
}
