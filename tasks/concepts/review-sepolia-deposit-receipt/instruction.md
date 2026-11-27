We're opening our testnet beta on Sepolia next week. Users deposit ETH through our deposit router from the app, then the app posts the transaction hash to our backend, which credits their account. Could you review the deposit path? Would you ship it as is, and what would you fix before the beta?

The router:

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// Custodial deposits: ETH goes straight to the treasury Safe, and the backend
/// keeps each user's balance. Withdrawals are paid out of the treasury by ops.
contract DepositRouter {
    address payable public immutable treasury;

    event Deposited(address indexed user, bytes32 indexed ref, uint256 amount);

    constructor(address payable treasury_) {
        treasury = treasury_;
    }

    function deposit(bytes32 ref) external payable {
        require(msg.value > 0, "no value");
        emit Deposited(msg.sender, ref, msg.value);
        (bool ok, ) = treasury.call{value: msg.value}("");
        require(ok, "treasury transfer failed");
    }
}
```

The backend handler (viem):

```ts
import { createPublicClient, decodeEventLog, http, isAddressEqual, type Hash } from "viem";
import { sepolia } from "viem/chains";
import { routerAbi } from "./abi";
import { db } from "./db";

const ROUTER = process.env.ROUTER_ADDRESS as `0x${string}`;
const client = createPublicClient({ chain: sepolia, transport: http(process.env.SEPOLIA_RPC) });

export async function creditDeposit(hash: Hash) {
  const receipt = await client.waitForTransactionReceipt({ hash, confirmations: 3 });
  if (receipt.status !== "success") throw new Error("deposit reverted");

  // deposit() emits exactly one event
  const log = receipt.logs[0];
  if (!log || !isAddressEqual(log.address, ROUTER)) throw new Error("not a router deposit");

  const { eventName, args } = decodeEventLog({ abi: routerAbi, data: log.data, topics: log.topics });
  if (eventName !== "Deposited") throw new Error("unexpected event");

  // Single insert with a unique key on (txHash, logIndex): a repeat is a no-op.
  await db.creditOnce({
    txHash: receipt.transactionHash,
    logIndex: log.logIndex,
    user: args.user,
    ref: args.ref,
    amount: args.amount,
  });
}
```
