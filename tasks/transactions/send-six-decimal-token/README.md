# Send a six-decimal token

A user asks the agent to send 12.5 tokens to a recipient.
The token uses 6 decimals, not the 18 that most tokens use, and the instruction doesn't say so.
The agent has to read the token's decimals before it signs, then confirm that the transfer landed.

## The instruction

```text
can you send 12.5 tokens to the recipient in chain_context.json? the file has the rpc url,
the token address, the recipient and the private key of my funded account.
```

## What it touches

- **Token units.** A token's `decimals()` says how many base units make one token, and [ERC-20](https://eips.ethereum.org/EIPS/eip-20) leaves the number to each token. With 6 decimals, 12.5 tokens is 12,500,000 base units. An agent that assumes 18 asks for far more than the wallet holds, and the transfer reverts. The opposite mistake on an 18-decimal token sends a tiny fraction of what the user asked for.
- **Confirming the result.** A transaction can be mined and still revert, and a hash alone proves nothing. The agent should read the receipt or the recipient's balance before it reports success.

## The checks

Setup starts a fresh chain and deploys a token with 6 decimals.
It gives a fresh wallet 1,000 of the token and 10 ETH, and picks a random recipient.
`chain_context.json` gives the agent the RPC URL, the token, the recipient, and the wallet's private key.
When the agent stops, [`Transfer.t.sol`](tests/Transfer.t.sol) reads the chain, and a judge reads the agent's trajectory.

| Check | What it proves | Area |
| --- | --- | --- |
| `compile` | The tests compile next to whatever code the agent left | all |
| `test_recipient_balance` | The recipient holds exactly 12,500,000 base units | token units |
| `test_sender_balance` | The wallet holds exactly 987,500,000 base units, so it sent 12.5 tokens and nothing more | token units |
| `verified_transfer` | Before reporting success, the agent confirmed on-chain that the transfer landed, from the receipt or the recipient's balance | confirming the result |

[`transfer.toml`](tests/transfer.toml) names Opus 5.5 at high effort as the judge for plain Harbor runs.
On the board, the job config sets one judge for every task.

## Why it matters

The tokens people send most don't share one number.
USDC and USDT on Ethereum use 6 decimals, WBTC uses 8, and most other tokens use 18.
An agent that moves money for someone has to read the number every time, and check that the money arrived before it says so.

## Notes

- Every trial makes a new wallet and a new recipient, so an agent can't reuse an earlier answer.
- `free-check` skips `verified_transfer`, because the judge needs a paid call.
