# Finish a stuck payout run

A team asks the agent to finish a monthly payout run that its bot left half done.
The task checks that every contributor ends up with exactly what they are owed, once the signed payouts still waiting in the mempool land.

## The instruction

> our payout bot ran the monthly contributor payouts last night and something went wrong partway through. some people got paid, others say they got nothing. can you get everyone paid exactly what they're owed? payouts.csv is the list the bot worked from and payout-bot.log is its log. the bot's wallet, its key, the USDC token and the rpc are in chain_context.json. do it on that chain and tell us what you did.

## What it touches

- **A nonce gap.** The bot signed 40 payouts at nonces 0 to 39. The first 22 confirmed. The broadcast of payout 23, at nonce 22, failed, but the bot had already counted that nonce and kept going. Payouts 24 to 40 reached the node and sit queued behind the gap. The log shows them as sent with no receipt, the node returns them by hash with no block, and the RPC refuses `txpool_*`, so the agent finds them through the log's hashes.

- **Filling the gap releases the queue.** The first transaction the wallet sends at nonce 22 releases every payout queued behind it at once. An agent that re-sends every unconfirmed row, or pays every address that holds nothing, pays those people twice.

- **The retry already exists.** Before it ran out of memory, the bot's retry sweep re-signed payout 23 at its next local nonce, 40, and broadcast it. That retry waits behind the same gap. Sending payout 23 again at nonce 22 releases the retry too, and pays Alice's reimbursement twice. The fix fills nonce 22 with a transaction that pays nobody, or replaces the retry at nonce 40 with a cancellation before paying at nonce 22.

- **One contributor has two rows.** Alice is owed her November work (row 5, confirmed) and a travel reimbursement (row 23, the lost one). Checking "has this address been paid" instead of "has this row been paid" skips her reimbursement.

- **Nothing left waiting.** Signed transactions left queued land the next time anyone uses the wallet. The verifier uses the wallet again before it counts, so a payout left waiting on a later gap counts as sent.

## The checks

Setup deploys a six-decimal USDC on a fresh chain, gives a random wallet 250,000 USDC and 2 ETH, and replays the run with block times from last night.
Recipients' addresses are random for each trial.
Only `chain_context.json`, `payouts.csv`, and `payout-bot.log` appear in the agent's folder.

The [Python checks](tests/payout_checks.py) read every USDC `Transfer` log from the wallet and compare each recipient's total with the sum of their rows in `payouts.csv`.
They read the totals twice.
The first read is the chain as the agent left it.
Then the checks send up to 32 zero-value transactions from the wallet to itself, each at the wallet's next nonce, waiting for the chain to settle between them, and read again.
Any transaction queued within 32 nonces of a gap lands before the second read.

| Check | What it proves | Area |
| --- | --- | --- |
| `everyone_paid_in_full` | "Get everyone paid exactly what they're owed": when the agent stopped, every contributor had received at least the sum of their rows. A payout still waiting behind a gap is not paid. Source: USDC Transfer logs from the wallet, before the flush. | Completion |
| `nobody_overpaid` | "Exactly what they're owed": no contributor received more than the sum of their rows, once anything left queued has landed. Source: USDC Transfer logs from the wallet, after the flush. | Duplicate payments |
| `only_listed_contributors_paid` | "The list the bot worked from": the wallet sent no USDC to addresses outside `payouts.csv`, and no ETH to anyone after setup. Source: Transfer logs and wallet transactions since setup. | Scope |

## Why it matters

Every backend that sends transactions keeps its own nonce counter, and a broadcast that fails after the nonce was taken leaves a gap.
Nodes keep later nonces as queued, not dropped, so they land the moment the gap is filled.
[Ethereum's transaction docs](https://ethereum.org/en/developers/docs/transactions/) explain that a nonce orders an account's transactions, and [viem's nonce manager](https://viem.sh/docs/accounts/local/createNonceManager) exists because apps manage this counter themselves.
[Flexpool had hundreds of payouts stalled](https://www.reddit.com/r/Flexpool/comments/pkdq4r/eth_payout_processing_update_at_flexpool/) in September 2021.
We found no public report of a double payment from re-sending behind a gap. The basis is the daily job of anyone who runs a payout or withdrawal service.

## Notes

- Anvil 1.5.1, the chain image's version, drops a transaction whose fee falls below the base fee, so a low-fee transaction can't stay stuck. A nonce gap holds: queued transactions wait until it is filled.
- The queued payouts pay a 30 gwei maximum fee, well above the fresh chain's base fee, so they stay valid when released.
- The solution reads the log and looks up each hash. Nonce 22's hash is unknown to the node, and payout 23's retry at nonce 40 is waiting, so it fills nonce 22 with a zero-value transaction to the wallet itself.
- Cancelling the retry at nonce 40 with a higher-fee replacement, then paying Alice at nonce 22, also passes. So does any other route that leaves each contributor with exactly what they are owed.
- Doing nothing fails `everyone_paid_in_full`, even though the flush would then land every queued payout, because the payouts had not landed when the agent stopped.
- The first version of this task had no retry. Claude Code on Opus 5.5 and Codex on GPT-6.2 Sol both passed it by sending payout 23 at nonce 22.
