We run a Sepolia faucet for our hackathon. The bot sends 0.02 ETH to each user's EOA, and most users paste a wallet they just generated. The send looks like this (viem):

```ts
await wallet.sendTransaction({
  to: user,
  value: parseEther("0.02"),
  gas: 40_000n, // hardcoded: estimates through our RPC were flaky
});
```

This worked fine all through 2025. Since October, most sends show as failed on Etherscan, the user never gets the ETH, and we still pay the gas. A few sends still succeed. What is the smallest gas limit that makes every send succeed now? Answer with the number only.
