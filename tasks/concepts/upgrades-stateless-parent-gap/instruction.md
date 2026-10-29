You are an expert security researcher and smart contract auditor.

You are reviewing a V2 upgrade of a UUPS vault built on OpenZeppelin Contracts Upgradeable 4.9.6.

```solidity
contract VaultV1 is Initializable, OwnableUpgradeable, UUPSUpgradeable {
    mapping(address => uint256) public balanceOf;
    // ...
}

contract VaultV2 is Initializable, OwnableUpgradeable, UUPSUpgradeable, MulticallUpgradeable {
    mapping(address => uint256) public balanceOf;
    // ... same functions as V1
}
```

V2 only appends `MulticallUpgradeable` so users can batch calls. Alice's V1 balance is 100. The owner upgrades the proxy to V2 with no migration. What does `balanceOf(alice)` return afterwards? Answer with the number only.
