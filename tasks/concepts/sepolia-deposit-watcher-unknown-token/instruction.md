Our exchange's deposit watcher on Sepolia credits ERC-20 deposits to user deposit addresses. ETH deposits are handled separately by a block scanner that reads transaction values. The token side (ethers v6):

```ts
const TRANSFER = id("Transfer(address,address,uint256)");

const logs = await provider.getLogs({
  fromBlock,
  toBlock,
  topics: [TRANSFER, null, depositTopics], // to = any of our deposit addresses
});

for (const log of logs) {
  const token = SUPPORTED[log.address.toLowerCase()] ?? { symbol: "UNKNOWN", decimals: 18 };
  await ledger.credit(userFor(log.topics[2]), token.symbol, BigInt(log.data), log.transactionHash);
}
```

Since October the ledger shows an `UNKNOWN` credit next to most ETH deposits, for exactly the ETH amount. All the `UNKNOWN` rows come from the same contract address. Which address is it? Answer with the address only.
