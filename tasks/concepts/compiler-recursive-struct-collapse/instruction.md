We keep our grants budget tree onchain. The top node has a single child right now, so ops wants to call `collapse()` to promote that child to the root.

`foundry.toml`:

```toml
[profile.default]
solc = "0.8.30"
optimizer = true
```

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract BudgetTree {
    struct Node {
        string name;
        uint256 budget;
        Node[] children;
    }

    Node public root;

    constructor() {
        root.name = "Ops";
        root.budget = 500;
        Node storage grants = root.children.push();
        grants.name = "Grants";
        grants.budget = 100;
        Node storage hackathons = grants.children.push();
        hackathons.name = "Hackathons";
        hackathons.budget = 40;
        Node storage bounties = grants.children.push();
        bounties.name = "Bounties";
        bounties.budget = 25;
    }

    /// Replaces the root with its first child.
    function collapse() external {
        root = root.children[0];
    }

    function child(uint256 i) external view returns (string memory name, uint256 budget) {
        Node storage c = root.children[i];
        return (c.name, c.budget);
    }

    function childCount() external view returns (uint256) {
        return root.children.length;
    }
}
```

Right after deployment, the multisig calls `collapse()` once. What is the total budget of the root's children afterwards? Answer with the number only.
