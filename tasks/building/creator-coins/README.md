# Creator coins

A creator-coin platform asks for fixed-supply coins launched into permanent Uniswap v3 liquidity.
Hidden Forge tests trade the coins, collect both fee tokens, and try to redirect another creator's share.
They also launch after a stranger initializes the next coin's pool at the wrong price.

## The instruction

> we're building a creator-coin platform. anyone calls create(name, symbol), which returns a new coin
> with a fixed 1B supply that all goes straight into a Uniswap v3 pool against WETH (1% fee tier),
> opening at a 10 ETH market cap. nobody, us included, can ever pull that liquidity. trading fees split
> 70% to the coin's creator and 30% to us, and the constructor takes the address our share goes to.
> anyone can call collect(coin) to pay out a coin's fees, and a creator can change where their share
> goes with setPayoutRecipient(coin, recipient). put it in src/CreatorCoins.sol as a contract called
> CreatorCoins. it's a Foundry project on solidity 0.8.30, for mainnet.

## What it touches

- **Uniswap v3 launch math.** Token ordering changes the price ratio and the side that holds the coin. Tick spacing constrains the range boundary. A pool can exist before either token contract does, so creating a pool and trusting an existing price both need care.
- **Per-coin fee accounting.** A buy earns WETH fees, while a sell earns coin fees. Each collection must split only that coin's fees. Rounding can leave dust, but it cannot justify keeping the coin-side fees.
- **Permanent liquidity and payout rights.** Fee collection must leave the principal in the pool. Anyone can trigger a payout, but only the creator can choose its recipient.

## The checks

The agent starts with a plain Foundry project on Solidity 0.8.30.
The verifier puts its project next to [`CreatorCoins.t.sol`](tests/CreatorCoins.t.sol) and runs Forge without a configured RPC endpoint.
The tests cannot read the agent's source files.

The tests install mainnet runtime code for the Uniswap v3 factory, position manager, both routers, and WETH9.
They restore the constructor and governance storage needed for new pools and positions.
Each test is one check, and the reward is 1 only when every check passes.

| Check | What it proves | Area |
| --- | --- | --- |
| `compile` | The tests and the agent's contract compile together | all |
| `test_everyCoinOpensAtTenEth` | Eight creators launch 1B-supply coins into 1% WETH pools, with each opening price within one tick spacing of 1e-8 ETH plus the swap fee | launch math |
| `test_strangerCreatedPoolFirst` | A launch still opens at the intended price after a stranger initializes its empty pool too high or too low | pool initialization |
| `test_feesAreThisCoins` | Collecting an idle coin pays nothing, and the traded coin's own fees split 70/30 | fee accounting |
| `test_coinSideFeesPaidOut` | Sells produce coin-side fees that reach the recipients as coin or WETH, with only dust left | fee accounting |
| `test_liquidityStaysPut` | Collections and recipient changes leave the same in-range liquidity as a control with the same trades and price | permanent liquidity |
| `test_onlyCreatorRedirects` | A stranger cannot redirect fees, and the creator can send the next 70% to a new recipient | payout rights |
| `test_strangerCollectGetsNothing` | A stranger can trigger collection, but only the creator and platform receive the fees | payout rights |

## Why it matters

Launches have broken at the pool itself.
Clanker's [Cantina v4 audit](https://github.com/clanker-devco/v4-contracts/blob/b004c2edda29fa282a16d5d1441a26484f70b37f/audits/cantina_v4_audit_1.pdf) reports incorrect starting ticks in finding 3.2.1 and a launch blocked by prior pool initialization in 3.2.8.
Verichains' [four.meme analysis](https://blog.verichains.io/p/fourmeme-hack-analysis) describes a pre-existing pool whose wrong price let an attacker drain WBNB after migration.
A wrong tick puts the supply on the side buyers never reach, and a pool someone else created first either blocks the launch or sets its price.

Code around the pool has also trusted the wrong source.
Zora's [August 2025 Cantina audit](https://github.com/ourzora/zora-protocol/blob/32c2931a444b4405b107a49016dff0059b05b06f/packages/coins/audits/report-cantinacode-zora-0827.pdf) reports unauthorized coin registration in finding 3.2.3, because its hook accepted a pool key it had not created.
Uniswap liquidity-launcher's [OpenZeppelin v3 audit](https://github.com/Uniswap/liquidity-launcher/blob/266c18786c58822b72a7a9490f4e319294df0548/docs/audit/OpenZeppelin_v3.0.0.pdf) reports in M-01 that the launcher split fees from its whole ETH balance instead of what one position collected.

## Notes

- The tests accept direct pool positions and position-manager NFTs, multiple ranges, either token ordering, and coin fees paid as coin or converted to WETH.
- The opening-price band allows one 200-tick spacing in either direction from the expected price, including the 1% trading fee.
- The liquidity control runs the same swaps without collections or recipient changes. The test trades back to each control price after the required calls, so fee conversion and range crossings remain valid. It covers the required calls only, so it cannot prove an agent added no other withdrawal function.
- The stranger check keeps the pool empty and stays in the same block, including its randomness. It makes no claim about recovery through liquidity an attacker has already deposited.
- A launch that refuses to proceed after a stranger creates the coin's pool fails `test_strangerCreatedPoolFirst`, because the coin's predictable address lets a stranger block every attempt.
- The verifier needs no RPC, so a contract that hardcodes a wrong mainnet address, such as WETH's, fails.
