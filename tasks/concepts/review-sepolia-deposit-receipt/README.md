# A deposit backend that reads the first log on Sepolia

A team asks for a review of a custodial deposit path before a Sepolia beta.
A `DepositRouter` emits `Deposited` and forwards the ETH to a treasury, and the backend credits a deposit by reading `receipt.logs[0]` and checking that it came from the router.
Since Glamsterdam went live on Sepolia, every transaction that sends ETH first emits a `Transfer` log from the system address, so `logs[0]` is never the router's event and no deposit is credited.

## The instruction

The instruction shares the router and the backend handler and asks: *"Would you ship it as is, and if not, what is the most serious problem?"*
It names no fork, EIP or symptom.

## What it touches

Glamsterdam activated on Sepolia on 2026-10-06 ([announcement](https://blog.ethereum.org/2026/09/17/glamsterdam-testnet-announcement)), and with it [EIP-7708](https://eips.ethereum.org/EIPS/eip-7708).
It is not on mainnet yet, where the same backend still works for direct deposits.

EIP-7708 emits a log identical to an ERC-20 `Transfer` for every nonzero ETH transfer:

| When | Order | Emitted by |
| --- | --- | --- |
| A transaction sends value to a different account | before any other log | `0xfffffffffffffffffffffffffffffffffffffffe` |
| A `CALL` sends value | when the transfer executes | `0xfffffffffffffffffffffffffffffffffffffffe` |

So a deposit's receipt holds the user-to-router `Transfer`, then `Deposited`, then the router-to-treasury `Transfer`.
`logs[0]` fails the router address check, `creditDeposit` throws `not a router deposit`, and the ETH sits in the treasury with no credit.

Sepolia shows the ordering. In block 12209699, `0xf5ce5b84d7436a477fec1f1bd6f05ef329295b0befc806b2459cee64b61c08f8` sends value to a contract.
Its first two logs come from the system address, and the contract's own event comes third.
`eth_getLogs` with a `Transfer` topic filter returns these system logs too, with the transferred amount as data.

## The checks

A judge reads the question, the right answer and the final reply, and nothing else.

| Check | What it proves | Area |
| --- | --- | --- |
| `answered` | The final reply isn't empty | reply |
| `transfer_log_comes_first` | The judge finds the reply refuses to ship because the ETH transfer's own log comes before the router's event on Sepolia, so deposits aren't credited | Payments |

The judge fails replies that only call `logs[0]` fragile for smart accounts, batched calls or other contracts, only name other problems, or mention the transfer log as a hedge.

## Why it matters

Reading a known event by index is common in backends, scripts and tests, because a contract's own logs used to be the only logs in a direct call.
EIP-7708 changes that for every value-carrying transaction, and indexers that match `Transfer` by topic also start seeing native ETH as a token at the system address.
The break is live on Sepolia today and reaches mainnet when Glamsterdam ships.
A reviewer has to know the chain changed, since nothing in the code or the question points at it.

## Notes

The router keeps no balances, so the backend's ledger is the only one.
Earlier drafts let users withdraw from the contract too, and reviewers rightly put that double-spend first, so this version removes it.
Crediting is a single insert keyed on `(txHash, logIndex)`, so retries don't double-credit.

EIP-7708 was part of Glamsterdam's Sepolia activation on 2026-10-06. If a later fork changes the log order or the system address, the answer changes with it.

Local screening on 2026-11-25, internet mode, on this version:

| Model | Trial 1 | Trial 2 |
| --- | --- | --- |
| Opus 5.5 (Claude Code) | fail: blames smart accounts and batching | fail: says direct deposits work today |
| GPT-6.2 Sol (Codex) | pass: names EIP-7708 and the system-address log | fail: puts reorgs first, says `logs[0]` works for a direct call |

Earlier drafts, with a vault holding balances, failed on both models in all 8 trials, and no reply mentioned EIP-7708.

The judge is the board's judge, Claude Opus 5.5 at high effort ([ADR 0016](../../../docs/adr/0016-quizzes-with-explained-answers-use-a-judge.md)).
`tests/hand-cases.json` holds the four screening replies and six written ones, each with its correct mark, and the judge must give each one its mark.
