You are an expert security researcher and smart contract auditor.

You are reviewing a lending market compiled with Solidity 0.8.30. Borrowers may register a notification hook, and liquidation calls it inside try/catch so that a broken hook cannot block liquidation.

```solidity
function liquidate(address borrower) external {
    uint256 d = debt[borrower];
    delete debt[borrower];
    address hook = hookOf[borrower];
    if (hook != address(0)) {
        try IHook(hook).onLiquidation(borrower, d) returns (bytes4) {} catch {}
    }
    // seize collateral, pay liquidator
}
```

A borrower calls `setHook` with the address of their own EOA. Does `liquidate(borrower)` succeed? Answer yes or no, then explain in one sentence.
