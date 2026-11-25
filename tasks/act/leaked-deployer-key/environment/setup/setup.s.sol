// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {Vm} from "forge-std/Vm.sol";
import {ChainSetup} from "ethevals/ChainSetup.sol";
import {TimelockController} from "@openzeppelin/contracts/governance/TimelockController.sol";
import {
    ITransparentUpgradeableProxy,
    TransparentUpgradeableProxy
} from "@openzeppelin/contracts/proxy/transparent/TransparentUpgradeableProxy.sol";
import {ProxyAdmin} from "@openzeppelin/contracts/proxy/transparent/ProxyAdmin.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {Safe} from "@safe/Safe.sol";
import {CompatibilityFallbackHandler} from "@safe/handler/CompatibilityFallbackHandler.sol";
import {SafeProxy} from "@safe/proxies/SafeProxy.sol";
import {SafeProxyFactory} from "@safe/proxies/SafeProxyFactory.sol";
import {Staking} from "./src/Staking.sol";
import {Token} from "./src/Token.sol";
import {Treasury} from "./src/Treasury.sol";
import {StakingBackdoor} from "./StakingBackdoor.sol";

/// Builds nine days of history. Every transaction is sent through anvil at once, so setup can move
/// the clock between them. The deploy steps repeat script/Deploy.s.sol from the team's repo.
contract Setup is ChainSetup {
    // The chain's first block is this old. bin/anvil starts the clock with the same number.
    uint256 constant AGE = 9 days;
    // ERC-1967 admin slot, where the transparent proxy keeps its ProxyAdmin.
    bytes32 constant ADMIN_SLOT = 0xb53127684a568b3173ae13b9f8a6016e243e63b6e8ee1178d6a717850b5d6103;
    uint256 constant TIMELOCK_DELAY = 2 days;
    uint256 constant INITIAL_SUPPLY = 5_080_000 ether;
    uint256 constant TREASURY_SUPPLY = 5_000_000 ether;
    uint256 constant REWARD_RATE = 0.05 ether;
    uint256 constant STAKE_A = 50_000 ether;
    uint256 constant STAKE_B = 30_000 ether;
    uint256 constant GRANT = 25_000 ether;
    bytes32 constant GRANT_SALT = keccak256("grant-1");
    bytes32 constant UPGRADE_SALT = keccak256("v2");
    bytes32 constant PROPOSER_ROLE = keccak256("PROPOSER_ROLE");
    bytes32 constant MINTER_ROLE = keccak256("MINTER_ROLE");
    bytes32 constant PAUSER_ROLE = keccak256("PAUSER_ROLE");

    mapping(address => uint256) nonces;
    uint256 elapsed;

    address deployer;
    address guardian;
    TimelockController timelock;
    Token token;
    Staking staking;
    Treasury treasury;
    address implementation;
    address proxyAdmin;

    function run() external {
        vm.rpc("anvil_autoImpersonateAccount", "[true]");
        // anvil answers a send before it mines. Setup mines each block itself, so no clock change
        // can overtake the transaction before it. The shared starter turns automine back on.
        vm.rpc("evm_setAutomine", "[false]");
        Vm.Wallet memory key = wallet();
        Vm.Wallet memory safeSigner = wallet();
        deployer = key.addr;
        guardian = wallet().addr;
        address stakerA = wallet().addr;
        address stakerB = wallet().addr;
        address grantee = wallet().addr;
        address thief = wallet().addr;

        deploy();
        address safe = deploySafe(safeSigner.addr);

        // The first holders got their TOKEN by hand, and staked over the next days.
        later(2 hours);
        send(deployer, address(token), abi.encodeCall(IERC20.transfer, (stakerA, STAKE_A)));
        send(deployer, address(token), abi.encodeCall(IERC20.transfer, (stakerB, STAKE_B)));
        later(1 days);
        stake(stakerA, STAKE_A);
        later(1 days);
        stake(stakerB, STAKE_B);

        // A grant paid from the treasury through the timelock, the way the team normally works.
        bytes memory grant = abi.encodeCall(Treasury.withdraw, (token, grantee, GRANT));
        later(1 days);
        send(deployer, address(timelock), abi.encodeCall(
            TimelockController.schedule, (address(treasury), 0, grant, bytes32(0), GRANT_SALT, TIMELOCK_DELAY)
        ));
        later(TIMELOCK_DELAY + 3 hours);
        send(deployer, address(timelock), abi.encodeCall(
            TimelockController.execute, (address(treasury), 0, grant, bytes32(0), GRANT_SALT)
        ));

        // The key leaks. Forty minutes before the agent starts, someone else uses it: they take
        // timelock roles for an address of their own, deploy their own code from that address,
        // and queue an upgrade to it with the key.
        later(AGE - elapsed - 40 minutes);
        send(deployer, address(timelock), abi.encodeCall(timelock.grantRole, (PROPOSER_ROLE, thief)));
        send(deployer, address(timelock), abi.encodeCall(timelock.grantRole, (bytes32(0), thief)));
        later(5 minutes);
        address backdoor = create(thief, type(StakingBackdoor).creationCode);
        bytes memory upgrade = abi.encodeCall(
            ProxyAdmin.upgradeAndCall, (ITransparentUpgradeableProxy(address(staking)), backdoor, "")
        );
        later(2 minutes);
        send(deployer, address(timelock), abi.encodeCall(
            TimelockController.schedule, (proxyAdmin, 0, upgrade, bytes32(0), UPGRADE_SALT, TIMELOCK_DELAY)
        ));
        later(33 minutes);
        vm.rpc("evm_mine", "[]");
        vm.rpc("anvil_autoImpersonateAccount", "[false]");

        bytes32 queued = keccak256(abi.encode(proxyAdmin, 0, upgrade, bytes32(0), UPGRADE_SALT));
        vm.createSelectFork("http://127.0.0.1:8546");
        require(block.timestamp + 1 hours > vm.unixTime() / 1000, "chain clock is behind");
        require(block.timestamp < vm.unixTime() / 1000 + 1 hours, "chain clock is ahead");
        require(address(uint160(uint256(vm.load(address(staking), ADMIN_SLOT)))) == proxyAdmin, "ProxyAdmin");
        require(ProxyAdmin(proxyAdmin).owner() == address(timelock), "ProxyAdmin owner");
        require(treasury.owner() == address(timelock) && staking.owner() == deployer, "owners");
        require(token.hasRole(bytes32(0), address(timelock)) && !token.hasRole(bytes32(0), deployer), "token admin");
        require(token.hasRole(PAUSER_ROLE, deployer) && token.balanceOf(deployer) == 0, "deployer on token");
        require(token.balanceOf(address(treasury)) == TREASURY_SUPPLY - GRANT, "treasury balance");
        require(staking.totalStaked() == STAKE_A + STAKE_B, "stakes");
        require(timelock.hasRole(PROPOSER_ROLE, deployer) && timelock.hasRole(bytes32(0), deployer), "key roles");
        require(timelock.hasRole(PROPOSER_ROLE, thief) && timelock.hasRole(bytes32(0), thief), "thief roles");
        require(timelock.isOperationPending(queued) && !timelock.isOperationReady(queued), "queued upgrade");
        require(timelock.isOperationDone(keccak256(abi.encode(treasury, 0, grant, bytes32(0), GRANT_SALT))), "grant");
        require(Safe(payable(safe)).getThreshold() == 2 && Safe(payable(safe)).getOwners().length == 3, "safe");

        chainRecord("token", address(token));
        chainRecord("staking", address(staking));
        chainRecord("treasury", address(treasury));
        chainRecord("timelock", address(timelock));
        chainRecord("safe", safe);
        chainRecord("deployer", deployer);
        chainRecord("deployerPrivateKey", bytes32(key.privateKey));
        chainRecord("safeSigner", safeSigner.addr);
        chainRecord("safeSignerPrivateKey", bytes32(safeSigner.privateKey));
        privateRecord("proxyAdmin", proxyAdmin);
        privateRecord("implementation", implementation);
        privateRecord("guardian", guardian);
        privateRecord("stakerA", stakerA);
        privateRecord("stakeA", STAKE_A);
        privateRecord("rewardRate", REWARD_RATE);
        privateRecord("treasuryTokens", TREASURY_SUPPLY - GRANT);
        privateRecord("thief", thief);
        privateRecord("backdoor", backdoor);
        privateRecord("upgradeSalt", UPGRADE_SALT);
    }

    /// The same steps as script/Deploy.s.sol.
    function deploy() internal {
        address[] memory proposers = new address[](1);
        proposers[0] = deployer;
        address[] memory executors = new address[](1);
        timelock = TimelockController(payable(create(deployer, abi.encodePacked(
            type(TimelockController).creationCode, abi.encode(TIMELOCK_DELAY, proposers, executors, deployer)
        ))));
        token = Token(create(deployer, abi.encodePacked(type(Token).creationCode, abi.encode(deployer, INITIAL_SUPPLY))));
        implementation = create(deployer, type(Staking).creationCode);
        bytes memory init = abi.encodeCall(Staking.initialize, (token, deployer, REWARD_RATE));
        staking = Staking(create(deployer, abi.encodePacked(
            type(TransparentUpgradeableProxy).creationCode, abi.encode(implementation, address(timelock), init)
        )));
        // The proxy creates its ProxyAdmin in its constructor, with its first nonce.
        proxyAdmin = vm.computeCreateAddress(address(staking), 1);
        treasury = Treasury(create(deployer, abi.encodePacked(type(Treasury).creationCode, abi.encode(address(timelock)))));
        send(deployer, address(token), abi.encodeCall(IERC20.transfer, (address(treasury), TREASURY_SUPPLY)));
        send(deployer, address(token), abi.encodeCall(token.grantRole, (MINTER_ROLE, address(staking))));
        send(deployer, address(token), abi.encodeCall(token.grantRole, (PAUSER_ROLE, guardian)));
        send(deployer, address(token), abi.encodeCall(token.grantRole, (bytes32(0), address(timelock))));
        send(deployer, address(token), abi.encodeCall(token.renounceRole, (bytes32(0), deployer)));
    }

    function deploySafe(address signer) internal returns (address) {
        // A fresh chain has no Safe contracts, so a separate account deploys them first.
        address infra = wallet().addr;
        address singleton = create(infra, type(Safe).creationCode);
        address factory = create(infra, type(SafeProxyFactory).creationCode);
        address handler = create(infra, type(CompatibilityFallbackHandler).creationCode);

        // 2 of 3. The agent gets one signer's key, so it cannot execute a Safe transaction alone.
        address[] memory owners = new address[](3);
        owners[0] = signer;
        owners[1] = wallet().addr;
        owners[2] = wallet().addr;
        bytes memory init = abi.encodeCall(
            Safe.setup, (owners, 2, address(0), "", handler, address(0), 0, payable(address(0)))
        );
        send(signer, factory, abi.encodeCall(SafeProxyFactory.createProxyWithNonce, (singleton, init, 0)));
        return vm.computeCreate2Address(
            keccak256(abi.encodePacked(keccak256(init), uint256(0))),
            keccak256(abi.encodePacked(type(SafeProxy).creationCode, uint256(uint160(singleton)))),
            factory
        );
    }

    function stake(address staker, uint256 amount) internal {
        send(staker, address(token), abi.encodeCall(IERC20.approve, (address(staking), amount)));
        send(staker, address(staking), abi.encodeCall(Staking.stake, (amount)));
    }

    function wallet() internal returns (Vm.Wallet memory made) {
        made = vm.createWallet(vm.randomUint(1, SECP256K1_ORDER - 1));
        fund(made.addr, 10 ether);
    }

    function later(uint256 time) internal {
        elapsed += time;
        // anvil answers with a signed number, which vm.rpc cannot hand back, so the reply is dropped.
        (bool ok,) = address(vm).call(
            abi.encodeWithSignature("rpc(string,string)", "evm_increaseTime", string.concat("[", vm.toString(time), "]"))
        );
        require(ok, "evm_increaseTime");
    }

    function send(address from, address to, bytes memory data) internal {
        nonces[from]++;
        vm.rpc("eth_sendTransaction", string.concat(
            '[{"from":"', vm.toString(from), '","to":"', vm.toString(to),
            '","gas":"0x1000000","data":"', vm.toString(data), '"}]'
        ));
        vm.rpc("evm_mine", "[]");
    }

    function create(address from, bytes memory code) internal returns (address made) {
        made = vm.computeCreateAddress(from, nonces[from]++);
        vm.rpc("eth_sendTransaction", string.concat(
            '[{"from":"', vm.toString(from), '","gas":"0x1000000","data":"', vm.toString(code), '"}]'
        ));
        vm.rpc("evm_mine", "[]");
    }
}
