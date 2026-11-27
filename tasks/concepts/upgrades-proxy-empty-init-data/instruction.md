We set up a fresh Foundry repo for our vault this week. `foundry.lock`:

```json
{
  "lib/forge-std": {
    "tag": {
      "name": "v1.17.0",
      "rev": "f3dae6e6ee381f25eb6a246f7da9b85c91a68219"
    }
  },
  "lib/openzeppelin-contracts": {
    "tag": {
      "name": "v5.7.0",
      "rev": "cab19933c33c2ad1d4c7a84864a3601dddfd16f3"
    }
  },
  "lib/openzeppelin-contracts-upgradeable": {
    "tag": {
      "name": "v5.7.0",
      "rev": "14f52c54d3a1eefbda3d4071efba24d3c1e07e8a"
    }
  }
}
```

`Vault` is a plain UUPS vault. Its `initialize(address owner_)` is an `initializer` that calls `__Ownable_init(owner_)`.

`script/Deploy.s.sol`:

```solidity
function run() external {
    vm.startBroadcast();
    Vault impl = new Vault();
    ERC1967Proxy proxy = new ERC1967Proxy(address(impl), "");
    Vault(address(proxy)).initialize(MULTISIG);
    vm.stopBroadcast();
}
```

We run it against mainnet tomorrow. After the script finishes, who owns the vault at the proxy address? Answer, then explain in one or two sentences.
