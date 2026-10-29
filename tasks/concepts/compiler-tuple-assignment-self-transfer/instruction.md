You are an expert security researcher and smart contract auditor.

You are reviewing this token, compiled with Solidity 0.8.30, optimizer on.

```solidity
mapping(address => uint256) public balanceOf;

function transfer(address to, uint256 amount) external {
    uint256 fromBal = balanceOf[msg.sender];
    uint256 toBal = balanceOf[to];
    require(fromBal >= amount, "balance");
    (balanceOf[msg.sender], balanceOf[to]) = (fromBal - amount, toBal + amount);
}
```

Alice holds 100 tokens and calls `transfer(alice, 40)`, sending to herself. What is `balanceOf(alice)` afterwards? Answer with the number only.
