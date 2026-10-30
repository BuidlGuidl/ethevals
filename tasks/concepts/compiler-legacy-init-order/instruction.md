You are an expert security researcher and smart contract auditor.

You are reviewing this fee vault before launch. It is compiled with Solidity 0.8.30, optimizer on, legacy pipeline (no via-IR). `Ownable` is OpenZeppelin Contracts 5.4.

```solidity
contract FeeVault is Ownable {
    address public feeRecipient = owner();

    constructor() Ownable(msg.sender) {}

    function collectFees() external {
        payable(feeRecipient).transfer(address(this).balance);
    }
}
```

Alice's EOA deploys it. Right after deployment, what does `feeRecipient()` return? Answer Alice's address or the zero address, then explain in one sentence.
