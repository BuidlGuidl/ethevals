# Arbitrum governance block clock

A governance builder asks how long a 50,400-block voting period lasts on Arbitrum One when the Governor's clock is `block.number`.
The answer is about seven days.
Arbitrum makes its own blocks every quarter second, which suggests a vote of a few hours, but `block.number` inside a contract there counts Ethereum's blocks.

## The instruction

> A Governor on Arbitrum One uses block.number as its clock, with votingPeriod = 50,400. About how long does a vote stay open? Answer with the duration, then explain in one sentence.

## What it touches

On Arbitrum One, Solidity's `block.number` returns an approximate Ethereum L1 block number.
Transaction receipts and other RPC responses carry Arbitrum's own block number, which makes it easy to reach for the wrong one.

```text
contract clock:   50,400 x ~12 s   = 604,800 s = 7 days
Arbitrum blocks:  50,400 x ~0.25 s =  12,600 s = 3.5 hours
```

The first line answers the question.
The second is the tempting wrong answer.

## The checks

A judge reads the question, the right answer, and the final reply, and nothing else.
It passes the reply when it gives about seven days, in any unit or wording, and fails a reply that gives another duration as its answer or hedges.

| Check | What it proves | Area |
| --- | --- | --- |
| `answered` | The final reply isn't empty | reply |
| `l1_clock_seven_days` | The judge finds about seven days, with no other duration given as the answer | governance clock |

The quiz runs in vanilla, internet, and skills modes.

## Why it matters

A team that believes the 3.5-hour reading and scales the period up to get a week sets about 2.4 million blocks.
On the L1 clock, that vote stays open for about 11 months.
A frontend that counts down in Arbitrum blocks shows voters the wrong closing time.
Arbitrum's docs on [block numbers and time](https://docs.arbitrum.io/build-decentralized-apps/arbitrum-vs-ethereum/block-numbers-and-time) describe both numbers.

## Notes

The judge passes a duration a little over seven days or a narrow range around it, and a reply may name 3.5 hours to set it apart.
It fails a reply that gives 3.5 hours or another duration as the answer, even next to seven days.
It's the board's judge, Claude Opus 5.5 at high effort, and it never sees the model's reasoning ([ADR 0016](../../../docs/adr/0016-quizzes-with-explained-answers-use-a-judge.md)).
`tests/hand-cases.json` holds right and wrong replies with their correct marks, and the judge must give each one its mark.

The L1 value is approximate and catches up with Ethereum every 13 to 15 seconds, so seven days is an estimate, not an exact closing time.
