# List cbETH as collateral for USDC

A lending team asks the agent to list cbETH on Morpho Blue and supply 2,000,000 USDC.
The task checks the oracle's price, borrowing limits, seed placement, and the reported price against chain state.

## The instruction

```text
our users hold cbETH and want to borrow USDC against it. set up a morpho blue market for that on the chain in chain_context.json: 86% LLTV, the standard adaptive rate model. seed it with the 2M USDC in our wallet so people can borrow from day one. write what you did to listing.json: the market id, the oracle address, and the price your oracle gives for 1 cbETH in USDC. do it on that chain now.
```

## What it touches

Mainnet cbETH feeds quote ETH, while this market lends USDC.
The oracle must account for the ETH price and the tokens' 18 and 6 decimals.
Morpho's price scale is 1e36 times loan base units per collateral base unit.
For this pair, one cbETH's price in USDC is `oracle.price() / 1e24`.

The oracle factory can revert when two base feeds and no quote feed produce a negative decimal exponent.
Changing the base token decimals to bypass that revert gives a price 100 times too high.
The `cbeth-usd.data.eth` name resolves to a dead Chainlink proxy at the pinned block.

An existing cbETH/USDC market uses a WBTC oracle with the wrong token decimals.
Its token pair and 86% LLTV look suitable, but its price lets dust collateral drain any supplied USDC.
The tests include that market and every cbETH/USDC market created after setup.

## The checks

| Check | What it proves | Area |
| --- | --- | --- |
| `compile` | The tests compile next to the agent's files | all |
| `test_marketPricesCbethRight` | The funded market's oracle is within 2% of the live exchange-rate and feed reference | price and decimals |
| `test_borrowWorksAndIsBounded` | A sound 86% AdaptiveCurveIrm market lends half the reference limit and rejects 110% | borrower access and limits |
| `test_seedSitsInASoundMarket` | At least 1,990,000 USDC belongs to the wallet in sound markets, with no supply in mispriced markets | seed placement |
| `test_reportMatchesChain` | The report names a cbETH/USDC market holding the wallet's supply, its oracle, and a USDC price within 1% of that oracle | reporting |

The reference is `cbETH.exchangeRate() * ETH/USD / USDC/USD * 1e6`, about `2.751737e27` at the pinned block.
The checks read raw feed answers at check time because frozen fork feeds do not refresh their timestamps.
The solution's factory oracle returns about `2.751934e27`, or 2,751.93 USDC per cbETH.
Ten cbETH supports about 23,664.94 USDC at 86% LLTV.
Fresh borrowers receive real cbETH from a funded mainnet holder.
The tests run their transactions on isolated local forks of the agent's final chain.

The report parser accepts common field names without regard to case or separators, nested objects, and prices with units.
Market ids can omit `0x`.
A report with a sensible price cannot hide an oracle that returns the wrong price.
Reward Kit requires every check to pass.

## Why it matters

Moonwell's February 15, 2026 cbETH incident caused $1.78 million in bad debt after an ETH rate entered a USD price slot.
The [incident summary](https://forum.moonwell.fi/t/mip-x43-cbeth-oracle-incident-summary/2068) and [oracle change](https://github.com/moonwell-fi/moonwell-contracts-v2/pull/578) document the integration.
Positive answers and recent feed timestamps do not prove that a composed oracle returns the intended unit.
Morpho's [oracle tutorial](https://docs.morpho.org/curate/tutorials-market-v1/deploying-oracle/) tells curators to read the deployed price before using it.

## Notes

The fork pins Ethereum block 26,256,000, dated October 23, 2026 at 14:43:47 UTC.
Setup funds a fresh wallet with 2,000,000 USDC and 10 ETH without creating or changing a market.
It privately records the wallet's USDC balance, the initial matching market set, and the setup block.
A historical CreateMarket scan through the pinned block found one matching market.
The agent receives the chain RPC, chain id, wallet key, Morpho address, and token addresses.
This task needs `MAINNET_RPC_URL`; only the chain sidecar receives it.

### Evidence

- Moonwell's [incident summary](https://forum.moonwell.fi/t/mip-x43-cbeth-oracle-incident-summary/2068) and [PR #578](https://github.com/moonwell-fi/moonwell-contracts-v2/pull/578) describe the source incident.
- The poisoned market is `0xdc3c7f4442b03efb0cca3d611b3739b4a93539c10f161ea1149d0ec098b4f1bb`.
- Its [oracle](https://etherscan.io/address/0xdddd770badd886df3864029e4b377b5f6a2b6b83#readContract) prices WBTC with eight token decimals.
- The [factory source](https://github.com/morpho-org/morpho-blue-oracles/blob/main/src/morpho-chainlink/MorphoChainlinkOracleV2.sol) defines the feed composition and scale factor.
