// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {SluiceFixture} from "./SluiceFixture.sol";
import {SluiceVault} from "../src/SluiceVault.sol";
import {SluiceConfig} from "../src/SluiceConfig.sol";
import {ERC20} from "../src/tokens/ERC20.sol";
import {LendingMarketStrategy} from "../src/strategies/LendingMarketStrategy.sol";
import {IERC4626} from "../src/interfaces/IERC4626.sol";
import {MockLendingMarket} from "./mocks/MockLendingMarket.sol";

contract SluiceConfigTest is SluiceFixture {
    LendingMarketStrategy internal strategyC;

    function setUp() public override {
        super.setUp();
        strategyC = new LendingMarketStrategy(address(vault), IERC4626(address(new MockLendingMarket(usdc))));
    }

    function test_performanceFeeRaiseWaitsForTimelock() public {
        vm.prank(owner);
        vault.submitPerformanceFee(2_000);
        assertEq(vault.performanceFee(), 1_500);

        vm.expectRevert(SluiceConfig.TimelockNotElapsed.selector);
        vault.acceptPerformanceFee();

        skip(1 days);
        vault.acceptPerformanceFee();
        assertEq(vault.performanceFee(), 2_000);
        (, uint64 validAt) = vault.pendingPerformanceFee();
        assertEq(validAt, 0);
    }

    function test_performanceFeeCutAppliesAtOnce() public {
        vm.prank(owner);
        vault.submitPerformanceFee(1_000);
        assertEq(vault.performanceFee(), 1_000);
    }

    function test_feesCapped() public {
        vm.startPrank(owner);
        vm.expectRevert(SluiceConfig.FeeTooHigh.selector);
        vault.submitPerformanceFee(3_001);
        vm.expectRevert(SluiceConfig.FeeTooHigh.selector);
        vault.submitManagementFee(201);
        vm.stopPrank();
    }

    function test_onlyOwnerSubmitsFees() public {
        vm.prank(curator);
        vm.expectRevert(SluiceConfig.Unauthorized.selector);
        vault.submitPerformanceFee(2_000);
    }

    function test_guardianRevokesPendingFee() public {
        vm.prank(owner);
        vault.submitPerformanceFee(2_500);
        vm.prank(guardian);
        vault.revokePendingPerformanceFee();

        skip(1 days);
        vm.expectRevert(SluiceConfig.NothingPending.selector);
        vault.acceptPerformanceFee();
        assertEq(vault.performanceFee(), 1_500);
    }

    function test_guardianRevokesPendingManagementFee() public {
        vm.prank(owner);
        vault.submitManagementFee(100);
        vm.prank(guardian);
        vault.revokePendingManagementFee();
        skip(1 days);
        vm.expectRevert(SluiceConfig.NothingPending.selector);
        vault.acceptManagementFee();
    }

    function test_strategyAdditionWaitsForTimelock() public {
        vm.prank(curator);
        vault.submitStrategy(strategyC, 500_000e6);
        vm.expectRevert(SluiceConfig.TimelockNotElapsed.selector);
        vault.acceptStrategy(strategyC);

        skip(1 days);
        vault.acceptStrategy(strategyC);
        (bool active, uint256 cap) = vault.strategies(strategyC);
        assertTrue(active);
        assertEq(cap, 500_000e6);
        assertEq(vault.withdrawQueueLength(), 3);
    }

    function test_submitStrategyChecksVaultAndAsset() public {
        SluiceVault other = new SluiceVault(usdc, "Other", "oUSDC", owner, treasury, 0, 0, 0);
        LendingMarketStrategy foreign =
            new LendingMarketStrategy(address(other), IERC4626(address(new MockLendingMarket(usdc))));
        vm.prank(curator);
        vm.expectRevert(SluiceVault.StrategyMismatch.selector);
        vault.submitStrategy(foreign, 1);
    }

    function test_guardianRevokesPendingStrategy() public {
        vm.prank(curator);
        vault.submitStrategy(strategyC, 500_000e6);
        vm.prank(guardian);
        vault.revokePendingStrategy(strategyC);
        skip(1 days);
        vm.expectRevert(SluiceConfig.NothingPending.selector);
        vault.acceptStrategy(strategyC);
    }

    function test_capRaiseWaitsAndCutIsImmediate() public {
        vm.prank(curator);
        vault.submitCap(strategyA, 2_000_000e6);
        (, uint256 cap) = vault.strategies(strategyA);
        assertEq(cap, 1_000_000e6);

        skip(1 days);
        vault.acceptCap(strategyA);
        (, cap) = vault.strategies(strategyA);
        assertEq(cap, 2_000_000e6);

        vm.prank(curator);
        vault.submitCap(strategyA, 0);
        (, cap) = vault.strategies(strategyA);
        assertEq(cap, 0);
    }

    function test_capCutClearsPendingRaise() public {
        vm.startPrank(curator);
        vault.submitCap(strategyA, 2_000_000e6);
        vault.submitCap(strategyA, 10e6);
        vm.stopPrank();
        skip(1 days);
        vm.expectRevert(SluiceConfig.NothingPending.selector);
        vault.acceptCap(strategyA);
    }

    function test_submitCapRejectsInactiveStrategy() public {
        vm.prank(curator);
        vm.expectRevert(SluiceVault.StrategyInactive.selector);
        vault.submitCap(strategyC, 1);
    }

    function test_timelockBounds() public {
        vm.startPrank(owner);
        vm.expectRevert(SluiceConfig.TimelockOutOfBounds.selector);
        vault.submitTimelock(1 days - 1);
        vm.expectRevert(SluiceConfig.TimelockOutOfBounds.selector);
        vault.submitTimelock(14 days + 1);

        vault.submitTimelock(3 days);
        assertEq(vault.timelock(), 3 days);

        vault.submitTimelock(2 days);
        vm.stopPrank();
        assertEq(vault.timelock(), 3 days);
        skip(3 days);
        vault.acceptTimelock();
        assertEq(vault.timelock(), 2 days);
    }

    function test_guardianRevokesPendingTimelock() public {
        vm.startPrank(owner);
        vault.submitTimelock(3 days);
        vault.submitTimelock(1 days);
        vm.stopPrank();
        vm.prank(guardian);
        vault.revokePendingTimelock();
        skip(3 days);
        vm.expectRevert(SluiceConfig.NothingPending.selector);
        vault.acceptTimelock();
    }

    function test_replacingGuardianWaits() public {
        address next = makeAddr("next");
        vm.prank(owner);
        vault.submitGuardian(next);
        assertEq(vault.guardian(), guardian);
        skip(1 days);
        vault.acceptGuardian();
        assertEq(vault.guardian(), next);
    }

    function test_guardianRevokesItsReplacement() public {
        vm.prank(owner);
        vault.submitGuardian(makeAddr("next"));
        vm.prank(guardian);
        vault.revokePendingGuardian();
        skip(1 days);
        vm.expectRevert(SluiceConfig.NothingPending.selector);
        vault.acceptGuardian();
    }

    function test_strangersCannotRevoke() public {
        vm.prank(curator);
        vault.submitCap(strategyA, 2_000_000e6);
        vm.prank(alice);
        vm.expectRevert(SluiceConfig.Unauthorized.selector);
        vault.revokePendingCap(strategyA);
        vm.prank(guardian);
        vault.revokePendingCap(strategyA);
    }

    function test_allocatorRoleCanBeRevoked() public {
        vm.prank(owner);
        vault.setIsAllocator(allocator, false);
        _deposit(alice, 1e6);
        vm.prank(allocator);
        vm.expectRevert(SluiceConfig.Unauthorized.selector);
        vault.allocate(strategyA, 1e6);
    }

    function test_setTreasury() public {
        address next = makeAddr("treasury2");
        vm.prank(owner);
        vault.setTreasury(next);
        assertEq(vault.treasury(), next);

        vm.prank(owner);
        vm.expectRevert(SluiceConfig.ZeroTreasury.selector);
        vault.setTreasury(address(0));
    }

    function test_twoStepOwnership() public {
        vm.prank(owner);
        vault.transferOwnership(bob);
        assertEq(vault.owner(), owner);
        vm.prank(bob);
        vault.acceptOwnership();
        assertEq(vault.owner(), bob);
    }

    function test_permitSetsAllowance() public {
        (address signer, uint256 key) = makeAddrAndKey("signer");
        uint256 deadline = block.timestamp + 1 hours;
        bytes32 structHash = keccak256(
            abi.encode(
                keccak256("Permit(address owner,address spender,uint256 value,uint256 nonce,uint256 deadline)"),
                signer,
                bob,
                1e12,
                0,
                deadline
            )
        );
        (uint8 v, bytes32 r, bytes32 s) =
            vm.sign(key, keccak256(abi.encodePacked("\x19\x01", vault.DOMAIN_SEPARATOR(), structHash)));

        vault.permit(signer, bob, 1e12, deadline, v, r, s);
        assertEq(vault.allowance(signer, bob), 1e12);
        assertEq(vault.nonces(signer), 1);

        vm.expectRevert(ERC20.InvalidSignature.selector);
        vault.permit(signer, bob, 1e12, deadline, v, r, s);

        skip(2 hours);
        vm.expectRevert(ERC20.PermitExpired.selector);
        vault.permit(signer, bob, 1e12, deadline, v, r, s);
    }
}
