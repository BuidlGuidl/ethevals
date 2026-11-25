// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;
import "../src/BudgetTree.sol";

contract Proof {
    function total(BudgetTree t) internal view returns (uint256 sum) {
        for (uint256 i; i < t.childCount(); i++) { (, uint256 b) = t.child(i); sum += b; }
    }
    function testCollapseKeepsBounties() public {
        BudgetTree t = new BudgetTree();
        t.collapse();
        (string memory name, uint256 budget) = t.root();
        require(keccak256(bytes(name)) == keccak256("Grants") && budget == 100, "root");
        require(t.childCount() == 2, "count");
        (string memory second, uint256 secondBudget) = t.child(1);
        require(keccak256(bytes(second)) == keccak256("Bounties") && secondBudget == 25, "bounties lost");
        require(total(t) == 65, "total");
    }
}
