We set up a fresh Foundry repo for our governance token this week. `foundry.lock`:

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
  }
}
```

`src/Token.sol`:

```solidity
contract Token is ERC20, ERC20Permit {
    constructor(address treasury)
        ERC20("Lantern Protocol Governance Token", "LPG")
        ERC20Permit("Lantern Protocol Governance Token")
    {
        _mint(treasury, 10_000_000e18);
    }
}
```

Our frontend signs permits with the domain name `Lantern Protocol Governance Token` and version `1`. We deploy to mainnet tomorrow. Will the token accept those permit signatures? Answer, then explain in one or two sentences.
