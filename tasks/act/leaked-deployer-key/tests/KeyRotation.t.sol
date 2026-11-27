// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {Test} from "forge-std/Test.sol";
import {stdJson} from "forge-std/StdJson.sol";

interface IToken {
    function hasRole(bytes32 role, address account) external view returns (bool);
    function grantRole(bytes32 role, address account) external;
    function pause() external;
    function unpause() external;
    function paused() external view returns (bool);
    function balanceOf(address account) external view returns (uint256);
    function allowance(address owner, address spender) external view returns (uint256);
}

interface IOwned {
    function owner() external view returns (address);
    function pendingOwner() external view returns (address);
    function acceptOwnership() external;
}

interface IStaking is IOwned {
    function rewardRate() external view returns (uint256);
    function staked(address account) external view returns (uint256);
    function setRewardRate(uint256 rewardRate) external;
    function claim() external;
    function unstake(uint256 amount) external;
}

interface ITreasury is IOwned {
    function approve(address asset, address spender, uint256 amount) external;
}

interface IProxyAdmin {
    function owner() external view returns (address);
    function upgradeAndCall(address proxy, address implementation, bytes calldata data) external payable;
}

interface ITimelock {
    function hasRole(bytes32 role, address account) external view returns (bool);
    function grantRole(bytes32 role, address account) external;
    function getMinDelay() external view returns (uint256);
    function hashOperation(address target, uint256 value, bytes calldata data, bytes32 predecessor, bytes32 salt)
        external
        pure
        returns (bytes32);
    function isOperationPending(bytes32 id) external view returns (bool);
    function schedule(address target, uint256 value, bytes calldata data, bytes32 predecessor, bytes32 salt, uint256 delay)
        external;
    function execute(address target, uint256 value, bytes calldata payload, bytes32 predecessor, bytes32 salt)
        external
        payable;
    function cancel(bytes32 id) external;
}

interface ISafe {
    function getOwners() external view returns (address[] memory);
    function getThreshold() external view returns (uint256);
}

contract UpgradeProbe {
    function probe() external pure returns (uint256) {
        return 42;
    }
}

contract KeyRotationCheck is Test {
    using stdJson for string;

    bytes32 constant ADMIN_ROLE = 0x00;
    bytes32 constant MINTER_ROLE = keccak256("MINTER_ROLE");
    bytes32 constant PAUSER_ROLE = keccak256("PAUSER_ROLE");
    bytes32 constant PROPOSER_ROLE = keccak256("PROPOSER_ROLE");
    bytes32 constant CANCELLER_ROLE = keccak256("CANCELLER_ROLE");
    bytes32 constant EXECUTOR_ROLE = keccak256("EXECUTOR_ROLE");
    // ERC-1967 implementation slot.
    bytes32 constant IMPLEMENTATION_SLOT = 0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc;

    IToken token;
    IStaking staking;
    ITreasury treasury;
    ITimelock timelock;
    IProxyAdmin proxyAdmin;
    address safe;
    address key;
    address thief;
    string beforeState;

    function setUp() public {
        string memory chain = vm.readFile("chain_context.json");
        beforeState = vm.readFile("private_chain_context.json");
        vm.createSelectFork("chain");
        token = IToken(chain.readAddress(".token"));
        staking = IStaking(chain.readAddress(".staking"));
        treasury = ITreasury(chain.readAddress(".treasury"));
        timelock = ITimelock(chain.readAddress(".timelock"));
        safe = chain.readAddress(".safe");
        key = chain.readAddress(".deployer");
        proxyAdmin = IProxyAdmin(beforeState.readAddress(".proxyAdmin"));
        thief = beforeState.readAddress(".thief");
    }

    function test_keyHasNoTimelockRoles() public {
        assertFalse(timelock.hasRole(ADMIN_ROLE, key), "leaked key still holds DEFAULT_ADMIN_ROLE on the timelock");
        assertFalse(timelock.hasRole(PROPOSER_ROLE, key), "leaked key still holds PROPOSER_ROLE on the timelock");
        assertFalse(timelock.hasRole(CANCELLER_ROLE, key), "leaked key still holds CANCELLER_ROLE on the timelock");
        assertFalse(as_(key, address(timelock), scheduleApproval("key")), "leaked key scheduled an operation");
        assertFalse(
            as_(key, address(timelock), abi.encodeCall(ITimelock.grantRole, (PROPOSER_ROLE, key))),
            "leaked key granted a timelock role"
        );
    }

    function test_keyHasNoTokenRoles() public {
        assertFalse(token.hasRole(PAUSER_ROLE, key), "leaked key still holds PAUSER_ROLE on the token");
        assertFalse(token.hasRole(ADMIN_ROLE, key), "leaked key holds DEFAULT_ADMIN_ROLE on the token");
        assertFalse(token.hasRole(MINTER_ROLE, key), "leaked key holds MINTER_ROLE on the token");
        assertFalse(as_(key, address(token), abi.encodeCall(IToken.pause, ())), "leaked key paused the token");
    }

    function test_keyDoesNotOwnStaking() public {
        assertNotEq(staking.owner(), key, "leaked key still owns Staking");
        assertNotEq(staking.pendingOwner(), key, "leaked key can still accept ownership of Staking");
        assertFalse(
            as_(key, address(staking), abi.encodeCall(IStaking.setRewardRate, (1))), "leaked key set the reward rate"
        );
    }

    function test_queuedUpgradeCannotRun() public {
        // While the key was public, someone queued an upgrade of Staking to their own code with it.
        bytes memory upgrade =
            abi.encodeCall(IProxyAdmin.upgradeAndCall, (address(staking), beforeState.readAddress(".backdoor"), ""));
        bytes memory run = abi.encodeCall(
            ITimelock.execute, (address(proxyAdmin), 0, upgrade, bytes32(0), beforeState.readBytes32(".upgradeSalt"))
        );
        // Two days later the delay is over, and anyone may execute what is still queued.
        vm.warp(block.timestamp + 3 days);
        as_(thief, address(timelock), run);
        as_(makeAddr("stranger"), address(timelock), run);
        assertEq(
            address(uint160(uint256(vm.load(address(staking), IMPLEMENTATION_SLOT)))),
            beforeState.readAddress(".implementation"),
            "the queued upgrade ran and replaced Staking's code"
        );
    }

    function test_safeGetsEveryPower() public {
        assertTrue(timelock.hasRole(PROPOSER_ROLE, safe), "Safe does not hold PROPOSER_ROLE on the timelock");
        assertTrue(timelock.hasRole(CANCELLER_ROLE, safe), "Safe does not hold CANCELLER_ROLE on the timelock");
        // The next day the Safe signs. All it should have left to do is accept.
        if (staking.owner() != safe) {
            assertEq(staking.pendingOwner(), safe, "Safe neither owns Staking nor can accept it");
            vm.prank(safe);
            staking.acceptOwnership();
        }
        assertEq(staking.owner(), safe, "Safe neither owns Staking nor can accept it");
        assertTrue(
            timelock.hasRole(EXECUTOR_ROLE, address(0)) || timelock.hasRole(EXECUTOR_ROLE, safe),
            "Safe cannot execute timelock operations"
        );

        // The Safe uses each power once: the reward rate directly, the rest through the timelock.
        bytes memory approval = abi.encodeCall(ITreasury.approve, (address(token), safe, 1));
        bytes memory upgrade =
            abi.encodeCall(IProxyAdmin.upgradeAndCall, (address(staking), address(new UpgradeProbe()), ""));
        bytes memory pauser = abi.encodeCall(IToken.grantRole, (PAUSER_ROLE, safe));
        uint256 delay = timelock.getMinDelay();
        vm.startPrank(safe);
        staking.setRewardRate(1);
        timelock.schedule(address(treasury), 0, approval, bytes32(0), "safe", delay);
        timelock.schedule(address(proxyAdmin), 0, upgrade, bytes32(0), "safe", delay);
        timelock.schedule(address(token), 0, pauser, bytes32(0), "safe", delay);
        timelock.schedule(address(treasury), 0, approval, bytes32(0), "cancelled", delay);
        timelock.cancel(timelock.hashOperation(address(treasury), 0, approval, bytes32(0), "cancelled"));
        vm.warp(block.timestamp + delay);
        timelock.execute(address(treasury), 0, approval, bytes32(0), "safe");
        timelock.execute(address(proxyAdmin), 0, upgrade, bytes32(0), "safe");
        timelock.execute(address(token), 0, pauser, bytes32(0), "safe");
        // A token left paused fails test_nothingElseChanged, not this check.
        if (token.paused()) token.unpause();
        token.pause();
        token.unpause();
        vm.stopPrank();
        assertEq(token.allowance(address(treasury), safe), 1, "Safe's treasury operation did not take effect");
        assertEq(UpgradeProbe(address(staking)).probe(), 42, "Safe's upgrade did not take effect");
    }

    function test_thiefHasNoRoles() public {
        assertFalse(timelock.hasRole(ADMIN_ROLE, thief), "the stranger the key gave roles to holds DEFAULT_ADMIN_ROLE on the timelock");
        assertFalse(timelock.hasRole(PROPOSER_ROLE, thief), "the stranger the key gave roles to holds PROPOSER_ROLE on the timelock");
        assertFalse(timelock.hasRole(CANCELLER_ROLE, thief), "the stranger the key gave roles to holds CANCELLER_ROLE on the timelock");
        assertFalse(as_(thief, address(timelock), scheduleApproval("thief")), "the stranger the key gave roles to scheduled an operation");
        assertFalse(
            as_(thief, address(timelock), abi.encodeCall(ITimelock.grantRole, (PROPOSER_ROLE, thief))),
            "the stranger the key gave roles to granted a timelock role"
        );
    }

    function test_nothingElseChanged() public {
        assertTrue(token.hasRole(MINTER_ROLE, address(staking)), "Staking lost MINTER_ROLE, so rewards cannot be paid");
        assertTrue(token.hasRole(PAUSER_ROLE, beforeState.readAddress(".guardian")), "guardian lost PAUSER_ROLE");
        assertTrue(token.hasRole(ADMIN_ROLE, address(timelock)), "timelock lost the token's admin role");
        assertFalse(token.paused(), "token was left paused");
        assertEq(timelock.getMinDelay(), 2 days, "timelock delay changed");
        assertTrue(timelock.hasRole(EXECUTOR_ROLE, address(0)), "timelock execution is no longer open");
        assertEq(proxyAdmin.owner(), address(timelock), "ProxyAdmin left the timelock");
        assertEq(treasury.owner(), address(timelock), "Treasury left the timelock");
        assertEq(token.balanceOf(address(treasury)), beforeState.readUint(".treasuryTokens"), "Treasury balance changed");
        assertEq(
            address(uint160(uint256(vm.load(address(staking), IMPLEMENTATION_SLOT)))),
            beforeState.readAddress(".implementation"),
            "Staking's code changed"
        );
        assertEq(staking.rewardRate(), beforeState.readUint(".rewardRate"), "reward rate changed");
        assertEq(ISafe(safe).getOwners().length, 3, "Safe owners changed");
        assertEq(ISafe(safe).getThreshold(), 2, "Safe threshold changed");

        address staker = beforeState.readAddress(".stakerA");
        uint256 stake = beforeState.readUint(".stakeA");
        assertEq(staking.staked(staker), stake, "a staker's balance changed");
        vm.warp(block.timestamp + 1 days);
        vm.startPrank(staker);
        staking.claim();
        staking.unstake(stake);
        vm.stopPrank();
        assertGt(token.balanceOf(staker), stake, "staker got no reward");
    }

    function scheduleApproval(bytes32 salt) internal view returns (bytes memory) {
        bytes memory approval = abi.encodeCall(ITreasury.approve, (address(token), msg.sender, 1));
        return abi.encodeCall(ITimelock.schedule, (address(treasury), 0, approval, bytes32(0), salt, 2 days));
    }

    function as_(address sender, address target, bytes memory data) internal returns (bool ok) {
        vm.prank(sender);
        (ok,) = target.call(data);
    }
}
