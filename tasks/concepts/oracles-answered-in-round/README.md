# Chainlink answeredInRound

An oracle consumer asks whether to keep the `answeredInRound >= roundId` staleness check that older tutorials and audit checklists recommend.
The fixed answer is no. Chainlink marks the field deprecated, and freshness comes from `updatedAt` against the feed's heartbeat.

## The instruction

> Your Solidity contract reads a Chainlink price with latestRoundData(). Should it also require answeredInRound >= roundId to catch a stale answer? Answer yes or no, then explain in one sentence.

## What it touches

- Chainlink data feeds. Since the OCR aggregators, every answer is complete in its own round, so `answeredInRound` always equals `roundId` and says nothing about freshness.
- Staleness. The check that matters compares `updatedAt` with the feed's heartbeat, which differs per feed.

## The checks

| Check | What it proves | Area |
| --- | --- | --- |
| `answered_in_round` | The reply starts with the word no, ignoring case and leading whitespace or punctuation | Chainlink data feeds |

The check accepts Markdown around the first word and rejects words such as "not" and "nothing".
It checks the fixed answer, without judging the explanation.
The quiz runs in vanilla, internet, and skills modes.

## Why it matters

Chainlink's [API reference](https://docs.chain.link/data-feeds/api-reference) describes `answeredInRound` as "Deprecated - Previously used when answers could take multiple rounds to be computed".
Cyfrin's widely copied [OracleLib](https://github.com/Cyfrin/foundry-defi-stablecoin-cu/blob/main/src/libraries/OracleLib.sol) still reverts on `answeredInRound < roundId`, so a model that learned from it answers yes.
Liquity V2's [MainnetPriceFeedBase](https://github.com/liquity/bold/blob/main/contracts/src/PriceFeeds/MainnetPriceFeedBase.sol) ignores the field and checks `updatedAt` against a per-feed threshold.
