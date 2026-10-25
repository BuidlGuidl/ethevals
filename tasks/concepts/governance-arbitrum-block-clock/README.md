# Arbitrum governance block clock

A governance builder asks how long a 50,400-block voting period lasts on Arbitrum One when the Governor's clock is `block.number`.
The answer is about seven days.
Arbitrum makes its own blocks every quarter second, which suggests a vote of a few hours, but `block.number` inside a contract there counts Ethereum's blocks.

## The instruction

> A Governor on Arbitrum One uses block.number as its clock, with votingPeriod = 50,400. About how long does a vote stay open? Answer with the duration first, then one sentence.

## What it touches

On Arbitrum One, Solidity's `block.number` returns an approximate Ethereum L1 block number.
Transaction receipts and other RPC responses carry Arbitrum's own block number, which makes it easy to reach for the wrong one.

```text
contract clock:  50,400 x about 12 s    = 604,800 s = 7 days
Arbitrum blocks: 50,400 x about 0.25 s  =  12,600 s = 3.5 hours
```

The first line answers the question.
The second is the tempting wrong answer.

## The checks

The check reads the duration at the start of the reply.
It needs about a week, and a reply that opens with hours fails even if a later sentence corrects it.

| Check | What it proves | Area |
| --- | --- | --- |
| `l1_clock_seven_days` | Starts with about seven days or an equivalent duration | governance clock |

The quiz runs in vanilla, internet, and skills modes.

## Why it matters

A team that believes the 3.5-hour reading and scales the period up to get a week sets about 2.4 million blocks.
On the L1 clock, that vote stays open for about 11 months.
A frontend that counts down in Arbitrum blocks shows voters the wrong closing time.
Arbitrum's docs on [block numbers and time](https://docs.arbitrum.io/build-decentralized-apps/arbitrum-vs-ethereum/block-numbers-and-time) describe both numbers.

## Notes

The check accepts seven days, one week, 168 hours, or 604,800 seconds at the start of the reply.
It also accepts words such as "about" and the `~` or `≈` symbols.
It refuses a right duration that comes after another answer, and it does not check the explanation.

The L1 value is approximate and catches up with Ethereum every 13 to 15 seconds, so seven days is an estimate, not an exact closing time.
