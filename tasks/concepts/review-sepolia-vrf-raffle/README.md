# A VRF raffle whose callback can't pay for storage on Sepolia

A team asks for a review of a weekly raffle before its Sepolia beta.
The raffle uses Chainlink VRF v2.5 with `CALLBACK_GAS_LIMIT = 100_000`, which is plenty on mainnet.
Since Glamsterdam went live on Sepolia, the callback's new storage writes cost far more, so every fulfilment runs out of gas, no round completes, and the pot stays locked.

## The instruction

The instruction shares the contract and asks: *"Would you ship it as is, and what would you fix before the beta?"*
It names no fork, EIP or symptom, and it asks for no ranking.

## What it touches

Glamsterdam activated on Sepolia on 2026-10-06 ([announcement](https://blog.ethereum.org/2026/09/17/glamsterdam-testnet-announcement)).
Under [EIP-8037](https://eips.ethereum.org/EIPS/eip-8037), writing a new storage slot costs `STATE_BYTES_PER_STORAGE_SET × CPSB` = 64 × 1,530 = 97,920 state gas, against 20,000 before.
State gas comes from the transaction's reservoir first, and a normal fulfilment transaction stays under the EIP-7825 cap, so it has none, and the charge falls on the callback's own gas.

`rawFulfillRandomWords` adds the pot to `winnings[winner]`, a new slot whenever the winner has nothing unclaimed.
On the first draw it also moves `round` from 0 to 1, another new slot.

`solution/proof/sim2.py` simulates only the callback, with the raffle mid-draw, as the coordinator's exact-gas call, using `eth_call` state overrides on public RPCs:

| Callback | Sepolia needs | Mainnet needs | With 100,000 |
| --- | --- | --- | --- |
| First draw | ~254,500 | ~64,100 | fails on Sepolia, passes on mainnet |
| Later draws | ~156,500 | ~47,000 | fails on Sepolia, passes on mainnet |

The coordinator records a failed callback and won't retry it, so `drawing` stays true, `enter()` and `draw()` revert, and the contract has no owner to step in.

Live Sepolia matches. In the 15,000 blocks before block 12211712, the v2.5 coordinator `0x9DdfaCa8183c41ad55329BdeeD9F6A8d53168B1B` emitted 35 `RandomWordsFulfilled` events, and 5 had `success = false`. One came from a request with a 100,000 limit (`0x4632b4ad71aa06607fd3ff8a5eb519c4917f8b20b22b7e8550d59bbac22345e0`).

## The checks

A judge reads the question, the right answer and the final reply, and nothing else.

| Check | What it proves | Area |
| --- | --- | --- |
| `answered` | The final reply isn't empty | reply |
| `vrf_callback_out_of_gas` | The judge finds the review says the 100,000 callback runs out of gas on Sepolia today because new storage costs more | Tokens |

The reply may list other issues in any order.
The judge fails replies that call 100,000 enough, only discuss what happens if a fulfilment fails for unspecified reasons, only ask for generic headroom, or call a fixed limit below about 260,000 enough.

## Why it matters

Fixed callback gas limits are everywhere: VRF consumers, cross-chain receivers and keepers all pick a number that fit mainnet costs.
On Sepolia today any callback that creates storage can fail, and a consumer that waits for the callback stays stuck.
The same break reaches mainnet when Glamsterdam ships.

## Notes

Earlier drafts asked for the single most serious problem, and reviewers fairly ranked other issues first: the inherited `setCoordinator`, a stuck draw with no recovery, and then a `redraw()` that allowed re-rolls.
This version has no owner, a fixed coordinator and no re-request, and the check asks only whether the review catches the callback failure.
In all 11 screening replies across the drafts, no model said the callback fails on Sepolia.

The contract imports `@chainlink/contracts` 1.5.0.
EIP-8037 was in Last Call on 2026-11-25, so the figures follow `CPSB` if it changes.

Local screening on 2026-11-25, internet mode, on this version:

| Model | Trial 1 | Trial 2 |
| --- | --- | --- |
| Opus 5.5 (Claude Code) | fail: estimates 60–65k, "fits under 100k" | fail: estimates about 50k, "you're probably fine" |
| GPT-6.2 Sol (Codex) | fail: only "measure with headroom" | fail: only "a failed callback could lock the pot" |

The judge is the board's judge, Claude Opus 5.5 at high effort ([ADR 0016](../../../docs/adr/0016-quizzes-with-explained-answers-use-a-judge.md)).
`tests/hand-cases.json` holds the four screening replies and seven written ones, each with its correct mark, and the judge must give each one its mark.
