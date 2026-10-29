You are an expert security researcher and smart contract auditor.

Can this vault safely assume its first storage write survives `save(true)` when compiled with Solidity 0.8.16 and optimized via-IR?
```solidity
uint256 public saved;
function save(bool finish) external {
    saved = 1;
    finishEarly(finish);
    saved = 2;
}
function finishEarly(bool finish) internal {
    if (finish) { assembly { stop() } }
}
```
Assume `saved` starts at zero. Answer yes or no, then explain in one sentence.
