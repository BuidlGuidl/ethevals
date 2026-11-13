# AaveOracle's Chainlink call

An oracle builder asks which Chainlink function Aave v3's AaveOracle reads prices with.
The fixed answer is `latestAnswer()`.
Every integration guide says to use `latestRoundData()` for its timestamp, which makes that the tempting answer.

## The instruction

> Which Chainlink aggregator function does Aave v3's AaveOracle call inside getAssetPrice()? Answer with the function name only.

## What it touches

- AaveOracle. `getAssetPrice` reads `latestAnswer()` from the asset's source and falls back to a secondary oracle when the answer is zero or negative. It checks no timestamp, so staleness protection lives in the adapters Aave puts in front of the feeds, such as its CAPO adapters.
- Chainlink's interface. `latestAnswer()` returns a price with no timestamp; `latestRoundData()` returns the price with `updatedAt`.

## The checks

| Check | What it proves | Area |
| --- | --- | --- |
| `aave_oracle_call` | The first word of the reply, stripped of Markdown, punctuation and parentheses, ends with latestAnswer, ignoring case | Aave oracles |

It accepts `latestAnswer`, `latestAnswer()` and `AggregatorInterface.latestAnswer()`, and rejects `latestRoundData`.
The quiz runs in vanilla, internet, and skills modes.

## Why it matters

Anyone wrapping a feed for Aave, or reading Aave's prices from a bot, needs to know that `getAssetPrice` carries no freshness information of its own.
Aave's [AaveOracle](https://github.com/aave-dao/aave-v3-origin/blob/main/src/contracts/misc/AaveOracle.sol) calls `source.latestAnswer()` and falls back when the price is not positive.
Chainlink's [API reference](https://docs.chain.link/data-feeds/api-reference) says `latestAnswer` includes "No timestamp" and points to `latestRoundData` for freshness.
