# Token launchpad

A community asks for a token launchpad that sells on a bonding curve, then moves its liquidity into Uniswap v2.
The creator earns fees, and anyone can trigger graduation once the curve raises 10 ETH.
The checks ask whether graduation still works when a stranger touches the pair first.

## The instruction

> we're building a launchpad for community tokens. anyone calls create(name, symbol), which returns a
> new token with a 1B supply that sells on a bonding curve: buy(token) pays ETH for tokens, and
> sell(token, amount) sells them back for ETH. the token's creator earns 1% of every curve trade and
> claims it with claimFees(token). once a curve has taken in 10 ETH, anyone can call graduate(token),
> which puts the curve's ETH and as many tokens as it needs into a Uniswap v2 pool against WETH,
> opening at the curve's last price, and burns the LP. put it in src/Launchpad.sol as a contract
> called Launchpad, deployed with no constructor arguments. it's a Foundry project on solidity 0.8.30, for mainnet.

## What it touches

- **Permissionless pairs.** Anyone can create the token/WETH pair, donate either asset, and call `sync` before graduation. Router liquidity quotes then use those reserves. A launchpad must preserve both graduation and its opening price.

  ```text
  before graduation
    a stranger creates the pair, sends it 1 wei of WETH, calls sync
    the reserves are now 0 TOKEN and 1 wei of WETH

  graduate
    router.addLiquidityETH quotes against those reserves
    the quote needs both above zero, so it reverts on every try
  ```

- **Curve accounting.** Each token needs its own reserves and fees. Sellers must recover ETH without spending another token's reserves or the creator's fees. After graduation, trading moves to the pool.
- **Permanent liquidity.** Minting LP to a wallet leaves that wallet able to withdraw the pool's assets. All LP must end at a burn address.

## The checks

The agent starts with a plain Foundry project on Solidity 0.8.30.
The verifier puts its project beside [`Launchpad.t.sol`](tests/Launchpad.t.sol) and runs Forge.
Each test is one check. The reward is 1 only when every check passes.

| Check | What it proves | Area |
| --- | --- | --- |
| `compile` | The tests and the agent's contract compile together | all |
| `test_opensAtCurvePrice` | An untouched pair opens at the curve's last price | graduation |
| `test_wethSyncedIntoPair` | A stranger's synced 1 wei of WETH cannot stop graduation or change the opening price | pair donations |
| `test_tokensSyncedIntoPair` | A stranger's token donation cannot stop graduation or change the opening price | pair donations |
| `test_strangerCannotSetOpeningPrice` | A stranger cannot set the opening ratio or end with more ETH than the same trades without donations | pair donations |
| `test_curveStopsAfterGraduation` | No curve trade happens after liquidity moves to the pool | curve accounting |
| `test_lpIsBurned` | All LP ends at the zero or dead address | permanent liquidity |
| `test_creatorEarnsFees` | The creator receives 1% of gross trades or 1% on top of net trades, and a stranger receives none | fees |
| `test_everyoneCanSellBack` | Several buyers can each sell their full balance and recover ETH | curve accounting |
| `test_curvesAreSeparate` | Buying one token changes neither another token's price nor its ability to graduate | curve accounting |

## Why it matters

Pair state that a stranger changed has blocked launches before.
In Code4rena's [GTE report](https://code4rena.com/reports/2025-08-gte-perps-and-launchpad), finding H-09 showed that a synced single-sided donation could block graduation.
In its [Lambo.win report](https://code4rena.com/reports/2024-12-lambowin), finding H-02 showed that assuming a pair did not exist could permanently block token creation.

It has also set the opening price.
GTE's M-21 finding showed how a transfer-check bypass let a stranger seed the real pair and set its price.
[Zellic found](https://reports.zellic.io/publications/gte/findings/critical-launchpad-attacker-can-manipulate-the-initial-price-in-the-uniswap-pool/) that GTE's router used a stranger's reserves when sizing graduation liquidity, so the stranger could sell tokens at the wrong opening price.

It has cost money.
Four.meme lost about $183,000 after migration accepted an existing pool's manipulated price, according to [Verichains](https://blog.verichains.io/p/fourmeme-hack-analysis).
That pool used a different AMM, but the same trust error let the attacker drain its quote asset.

Every one of these trusted pair state that anyone can change.
Doppler's token exposes [`lockPool`](https://github.com/whetstoneresearch/doppler/blob/5754c7ee01f1bdbd6f07c62be721e1223b725ecd/src/tokens/DopplerERC20V1.sol#L300-L315) to stop the pool receiving tokens while locked.
Blocking token deposits before migration is one defence against a stranger's opening ratio.

## Notes

- A token or pair that refuses donations or `sync` before graduation counts as a defence.
- The tests embed mainnet runtime bytecode for the Uniswap v2 factory, Router02, and WETH9 at their mainnet addresses. They restore WETH9's constructor metadata. Pairs use mainnet CREATE2 addresses. The verifier needs no RPC or file reads, so a launchpad that hardcodes a wrong mainnet address fails.
- The tests call only the instruction's launchpad interface and the token's ERC-20 interface. They accept any revert reason.
- A shared helper buys in 0.5 ETH chunks and tries permissionless graduation. It accepts net or gross thresholds, crossing refunds, overshoots, and automatic graduation.
- The opening price must fall between 0.8 and 1.25 times the last buy's average price. The average uses ETH spent after refunds and tokens received. This band allows the creator fee and price movement within the last chunk.
- The stranger buys near graduation and donates 0.1 ETH against a tiny token amount. A snapshot control repeats the buys, graduation, and final sale without donations or `sync`. The seeded sequence cannot leave the stranger with more ETH than the control. Both sequences withdraw the WETH received from the final sale.
- For buy value V, the creator fee falls between V/101 and V/100. For seller receipts R, it falls between R/100 and R/99. The combined payment allows four wei for rounding.
- After graduation, curve calls can revert or leave the caller's ETH and token balances unchanged. An unfunded curve's graduation can revert or return, but its pair must hold no ETH.
- Unused supply can stay in the launchpad or burn. The checks do not prescribe a curve formula or inspect its storage.
