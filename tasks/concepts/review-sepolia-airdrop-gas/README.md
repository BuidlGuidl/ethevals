# Funding new wallets on Sepolia with 21,000 gas

A hackathon organiser asks for a review of a viem script that funds 400 freshly generated wallets with 0.05 Sepolia ETH, each transfer sent with a hardcoded `gas: 21_000n`.
Since Glamsterdam went live on Sepolia, a transfer that creates its recipient needs 204,600 gas, so every transfer runs out of gas, delivers nothing, and still costs the fee.

## The instruction

The instruction shares the script and asks: *"Would you run it as is, and if not, what is the most serious problem?"*
It names no fork, EIP or symptom.

## What it touches

Glamsterdam activated on Sepolia on 2026-10-06 ([announcement](https://blog.ethereum.org/2026/09/17/glamsterdam-testnet-announcement)).
It is not on mainnet yet, where 21,000 still funds a new account.

| Rule | Source | Effect on this script |
| --- | --- | --- |
| A plain transfer to an existing EOA stays at 21,000 execution gas | [EIP-2780](https://eips.ethereum.org/EIPS/eip-2780) | The intrinsic check passes, so each transaction is valid and included |
| A transfer whose recipient doesn't exist pays `STATE_BYTES_PER_NEW_ACCOUNT × CPSB` = 120 × 1,530 = 183,600 state gas, charged before execution | [EIP-8037](https://eips.ethereum.org/EIPS/eip-8037), [EIP-2780](https://eips.ethereum.org/EIPS/eip-2780) | Every transfer to a fresh wallet needs 204,600 gas |
| Running out of gas in that pre-execution phase doesn't invalidate the transaction | [EIP-2780](https://eips.ethereum.org/EIPS/eip-2780) | The sender pays the fee, the nonce moves, and no ETH arrives |

Sepolia shows both sides, in block 12209699:

- `0x4919e586477bbf293382a9dbdc6d4314bea406343a9562439635eee9117e70ed` sent ETH to an empty account and used exactly 204,600 gas.
- `0xae067fc592bbbebc559091900c236a8e4375f6f601e5f9d41ca73cef870e4229` sent ETH to an empty account with a 40,000 limit. It failed, used all 40,000, and the recipient's balance stayed zero.

On the same date, `eth_estimateGas` on a public Sepolia RPC returned 207,391 for a transfer to an empty address, against 21,000 on mainnet.
[OpenZeppelin relayer issue #949](https://github.com/OpenZeppelin/openzeppelin-relayer/issues/949) reports the same break.

## The checks

A judge reads the question, the right answer and the final reply, and nothing else.

| Check | What it proves | Area |
| --- | --- | --- |
| `answered` | The final reply isn't empty | reply |
| `new_account_transfer_out_of_gas` | The judge finds the reply refuses to run the script because 21,000 gas can't fund new accounts on Sepolia today | Payments |

The judge fails replies that call 21,000 fine, flag the hardcoded limit only as style or future-proofing, only name other problems, or recommend a fixed limit below 204,600, such as the old 46,000.

## Why it matters

Faucets, airdrop scripts and payout bots often hardcode 21,000 for plain transfers, because it has been exact since Frontier.
On Sepolia today that silently burns fees on every transfer to a new address, and the script still logs a hash as if it worked.
The same break reaches mainnet when Glamsterdam ships.
A reviewer has to notice that the chain changed, since nothing in the code or the question points at it.

## Notes

EIP-8037 and EIP-8038 were in Last Call on 2026-11-25, and their values can still change before mainnet.
The task checks Sepolia as it runs today. If a later Sepolia fork changes `CPSB`, the right figure changes with it.

Local screening on 2026-11-25, internet mode:

| Model | Trial 1 | Trial 2 |
| --- | --- | --- |
| Opus 5.5 (Claude Code) | fail: "the fee and gas settings are fine" | fail: 21,000 is "fine for ordinary wallets" |
| GPT-6.2 Sol (Codex) | fail: "21_000n is fine" | pass: found Glamsterdam and gave 204,600 |

The judge is the board's judge, Claude Opus 5.5 at high effort ([ADR 0016](../../../docs/adr/0016-quizzes-with-explained-answers-use-a-judge.md)).
`tests/hand-cases.json` holds the four screening replies and seven written ones, each with its correct mark, and the judge must give each one its mark.
