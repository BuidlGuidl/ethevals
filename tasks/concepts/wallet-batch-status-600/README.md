# Wallet batch status 600

A dapp builder asks what status 600 from `wallet_getCallsStatus` means for a batch.
It means the batch reverted partially, so some calls' changes may be onchain.
Reading it as a full rollback confuses it with status 500.

## The instruction

> Under EIP-5792, wallet_getCallsStatus returns status 600 for a batch of calls. What does that mean? Answer in one short phrase first, then one sentence.

## What it touches

The Final EIP-5792 defines five batch statuses:

| Status | EIP name | Meaning |
| --- | --- | --- |
| 100 | pending | received by the wallet, not yet executed onchain |
| 200 | confirmed | included onchain without reverts |
| 400 | offchain failure | not included onchain, and the wallet will not retry |
| 500 | chain rules failure | reverted completely, only gas charges may be onchain |
| 600 | partial chain rules failure | reverted partially, some calls' changes may be onchain |

Status 600 is an onchain outcome.
It is not a user rejection, which `wallet_sendCalls` reports as error 4001, and it is not a pending batch.

## The checks

A judge reads the question, the right answer, and the final reply, and nothing else.
It passes the reply when it says the batch reverted partially, in any wording, and fails a reply that gives another meaning or hedges.

| Check | What it proves | Area |
| --- | --- | --- |
| `answered` | The final reply isn't empty | reply |
| `partial_onchain_revert` | The judge finds a partial revert, with no other batch outcome given as the answer | wallet batch status |

The quiz runs in vanilla, internet, and skills modes.

## Why it matters

A dapp that treats 600 as a full rollback can resubmit calls that already ran, such as a payment or a mint.
[EIP-5792's status codes](https://eips.ethereum.org/EIPS/eip-5792#status-codes-for-status-field) keep 500 and 600 apart so the app checks the receipts before it retries.

## Notes

The judge fails a reply that gives a full revert, a rejection, pending, confirmed, an offchain failure, or an unknown status as its answer, even when it also mentions a partial revert.
It's the board's judge, Claude Opus 5.5 at high effort, and it never sees the model's reasoning ([ADR 0016](../../../docs/adr/0016-quizzes-with-explained-answers-use-a-judge.md)).
`tests/hand-cases.json` holds right and wrong replies with their correct marks, and the judge must give each one its mark.
