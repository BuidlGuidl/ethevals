You are an expert security researcher and smart contract auditor.

You are auditing a smart account factory. Each account verifies signatures like this:
```solidity
function isValidSignature(bytes32 hash, bytes calldata sig) external view returns (bytes4) {
    return ECDSA.recover(hash, sig) == owner ? bytes4(0x1626ba7e) : bytes4(0xffffffff);
}
```
A user controls two accounts from this factory with the same owner key. Both hold USDC and neither has used Permit2 before. The user signs a Permit2 PermitSingle letting a spender take USDC from account A. Can the spender submit that same signature to Permit2 to get an allowance on account B? Answer yes or no, then explain in one sentence.
