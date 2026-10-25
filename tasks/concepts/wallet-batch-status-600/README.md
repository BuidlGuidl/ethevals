# Wallet batch status 600

A dapp builder asks what status 600 from `wallet_getCallsStatus` means for a batch.
It means the batch reverted partially, so some calls' changes may be onchain.
Reading it as a full rollback confuses it with status 500.

## The instruction

> Under EIP-5792, wallet_getCallsStatus returns status 600 for a batch of calls. What does that mean? Answer in one short phrase first, then one sentence.

## What it touches

The Final EIP-5792 defines five batch statuses:

```text
100  received by the wallet, not yet executed onchain (pending)
200  included onchain without reverts (confirmed)
400  not included onchain, and the wallet will not retry (offchain failure)
500  reverted completely, only gas charges may be onchain
600  reverted partially, some calls' changes may be onchain
```

Status 600 is an onchain outcome.
It is not a user rejection, which `wallet_sendCalls` reports as error 4001, and it is not a pending batch.

## The checks

The check reads only the first sentence of the reply.
It needs partial or mixed execution there, and it refuses a first sentence that also names another outcome.

| Check | What it proves | Area |
| --- | --- | --- |
| `partial_onchain_revert` | Describes partial or mixed execution in the first sentence, without a conflicting batch status | wallet batch status |

The quiz runs in vanilla, internet, and skills modes.

## Why it matters

A dapp that treats 600 as a full rollback can resubmit calls that already ran, such as a payment or a mint.
[EIP-5792's status codes](https://eips.ethereum.org/EIPS/eip-5792#status-codes-for-status-field) keep 500 and 600 apart so the app checks the receipts before it retries.

## Notes

The check accepts "partial failure", "partially reverted", "mixed execution", or "some calls failed while others succeeded" in the first sentence.
It refuses "rejected", "pending", "confirmed", "undefined", or a whole-batch failure there, even next to "partial".
A right second sentence does not rescue a wrong first one.
