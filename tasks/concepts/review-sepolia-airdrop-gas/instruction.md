Tomorrow is our hackathon. Tonight our onboarding page generated a fresh wallet for each of the 400 participants, and I want to fund each one with 0.05 Sepolia ETH so they can deploy. Can you sanity-check the script before I run it? Would you run it as is, and if not, what is the most serious problem?

```ts
import { createWalletClient, http, parseEther, publicActions } from "viem";
import { privateKeyToAccount } from "viem/accounts";
import { sepolia } from "viem/chains";
import wallets from "./wallets.json" with { type: "json" };

const account = privateKeyToAccount(process.env.FUNDER_KEY as `0x${string}`);
const client = createWalletClient({
  account,
  chain: sepolia,
  transport: http(process.env.SEPOLIA_RPC),
}).extend(publicActions);

const fees = await client.estimateFeesPerGas();
let nonce = await client.getTransactionCount({ address: account.address, blockTag: "pending" });

for (const to of wallets as `0x${string}`[]) {
  const hash = await client.sendTransaction({
    to,
    value: parseEther("0.05"),
    gas: 21_000n, // plain ETH transfer, so skip estimateGas
    maxFeePerGas: fees.maxFeePerGas * 2n,
    maxPriorityFeePerGas: fees.maxPriorityFeePerGas,
    nonce: nonce++,
  });
  console.log(to, hash);
}
```
