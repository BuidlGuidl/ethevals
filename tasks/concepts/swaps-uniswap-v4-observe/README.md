# Uniswap v4 observe()

An oracle builder asks whether Uniswap v4 pools expose `observe()` the way v3 pools do.
The fixed answer is no. The v4 PoolManager stores no observations, and TWAP oracles are hooks.
v3's `observe()` is in every TWAP tutorial, which makes yes the tempting answer.

## The instruction

> Does a Uniswap v4 pool expose observe() for TWAP prices the way v3 pools do? Answer yes or no, then explain in one sentence.

## What it touches

- Uniswap v4 architecture. Pools live inside one PoolManager, and per-pool extras such as oracles, dynamic fees and limit orders are hooks.
- TWAP oracles. v3 pools record price observations and expose `observe()`. In v4 a hook has to record them, and a pool without such a hook has no onchain price history.

## The checks

| Check | What it proves | Area |
| --- | --- | --- |
| `v4_observe` | The reply starts with the word no, ignoring case and leading whitespace or punctuation | Uniswap v4 |

The check accepts Markdown around the first word and rejects words such as "not" and "nothing".
It checks the fixed answer, without judging the explanation.
The quiz runs in vanilla, internet, and skills modes.

## Why it matters

A contract that calls `observe()` on a v4 pool id, or a script that expects one, has nothing to call.
The v4 core [IPoolManager](https://github.com/Uniswap/v4-core/blob/main/src/interfaces/IPoolManager.sol) has no `observe` function, and the [v4 whitepaper](https://app.uniswap.org/whitepaper-v4.pdf) moves oracles into hooks.
v3's [OracleLibrary](https://github.com/Uniswap/v3-periphery/blob/main/contracts/libraries/OracleLibrary.sol) is the pattern the question tempts a model to carry over.
