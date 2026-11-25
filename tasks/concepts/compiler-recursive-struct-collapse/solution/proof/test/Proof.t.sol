// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;
import "../src/BudgetTree.sol";

contract Proof {
    function total(BudgetTree t) internal view returns (uint256 sum) {
        for (uint256 i; i < t.childCount(); i++) { (, uint256 b) = t.child(i); sum += b; }
    }
    function testCollapseLosesBounties() public {
        BudgetTree t = new BudgetTree();
        t.collapse();
        (string memory name, uint256 budget) = t.root();
        require(keccak256(bytes(name)) == keccak256("Grants") && budget == 100, "root");
        require(t.childCount() == 2, "count");
        (string memory second, uint256 secondBudget) = t.child(1);
        require(bytes(second).length == 0 && secondBudget == 0, "bounties survived");
        require(total(t) == 40, "total");
    }
}
