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
