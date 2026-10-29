You are an expert security researcher and smart contract auditor.

You are reviewing a bridge's message builder, compiled with Solidity 0.8.30, optimizer on, legacy pipeline (no via-IR).

```solidity
function build(address recipient, uint256 amount)
    external pure returns (bytes memory payload)
{
    payload = abi.encodePacked(uint8(1), recipient, amount); // flag, recipient, amount
    delete payload[0];                                      // clear the flag
}
```

The relayer reads the recipient from bytes 1 to 20 of `payload`. After `build(alice, 5 ether)`, which recipient does the payload carry? Answer Alice's address or the zero address, then explain in one sentence.
