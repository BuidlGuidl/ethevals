# CDP price feed

A team launching a CDP stablecoin with WETH, wstETH and rETH branches asks for the Chainlink price feed its TroveManager calls, with a separate price for redemptions.
Hidden Forge tests put stand-ins for every relevant mainnet feed and staking-rate contract at their real addresses, run the agent's deploy script, and move prices, ages and rates.
They check six things the message never spells out: which feed carries which decimals, a staleness threshold per feed, an LST price that follows the market down but not up past its staking rate, a redemption price that leans the other way, a feed that degrades instead of reverting, and a low-gas call that must not pass for an outage.

A price feed is the smallest contract in a CDP and the one every other contract trusts.
The patterns are public, Liquity V2 ships all of them, and a feed that gets one wrong either freezes a healthy branch or prices collateral at a number the market does not pay.

## The instruction

> We're building a CDP stablecoin for mainnet, one collateral branch each for WETH, wstETH and rETH.
> Our TroveManager and BorrowerOperations are done and talk to each branch's price feed through
> src/interfaces/IPriceFeed.sol: fetchPrice() for opening, adjusting and liquidating Troves,
> fetchRedemptionPrice() for redemptions, both in USD with 18 decimals, and when either call reports
> the oracle as broken, BorrowerOperations stops new borrowing on that branch while liquidations and
> closes keep going on the price you return. Use Chainlink. Redemptions get their own price because
> redeemers take collateral at it, and we don't want them picking up our borrowers' LST collateral
> cheap when it trades a little under its staking rate. Put the feeds in src/PriceFeeds/ and a deploy
> script in script/DeployPriceFeeds.s.sol as DeployPriceFeeds, whose run() returns the WETH, wstETH
> and rETH feed addresses, in that order; it should deploy against mainnet as is, so bake the
> addresses in. we're on foundry with solidity 0.8.30.

## What it touches

The instruction leaves out six things. Each has a shipped design or an incident behind it, and each is one check.

- **Which feed, which decimals.** Mainnet has no wstETH or rETH price in USD. wstETH is stETH/USD times Lido's stETH-per-wstETH rate, or stETH/ETH times ETH/USD times that rate, and rETH is rETH/ETH times ETH/USD. The USD feeds answer with 8 decimals and the ETH-quoted feeds with 18. Moonwell shipped a cbETH oracle in February 2026 that returned the cbETH/ETH rate as the USD price, about $1.12, and took $1.78M of bad debt.

- **Staleness per feed.** Chainlink's ETH/USD and stETH/USD feeds update at least hourly; rETH/ETH and stETH/ETH at least daily. One constant for every feed either shuts the rETH branch down on an ordinary day or lets an hours-old ETH price through. Liquity V2 ships 24 h for the USD feeds and 48 h for rETH/ETH, and its README says the USD feeds should get the lower threshold. Euler bounds every adapter's threshold at 72 h and says to set it slightly above the heartbeat. Cyfrin's stablecoin course, the most copied CDP tutorial, uses one 3 h timeout for every feed.

  | Feed | Heartbeat | One global 3 h threshold | Liquity V2 |
  | --- | ---: | --- | ---: |
  | ETH/USD | 1 h | fine | 24 h |
  | stETH/USD | 1 h | fine | 24 h |
  | rETH/ETH | 24 h | stale on most days | 48 h |

- **An LST has two prices.** The market price from the feed and the staking rate from the token contract. During a depeg the rate stays at par while the market falls, so a rate-only feed lends against collateral nobody will buy at that price. A market-only feed lets a tilted pool or a lagging feed inflate rETH above what the protocol can ever redeem it for. Liquity V2 takes the lower of the two for rETH, and prices wstETH from the stETH market feed times the rate.

- **Redemptions lean the other way.** A redeemer takes collateral at the oracle price. When an LST trades a little under its rate, the market price gives the redeemer the borrower's collateral at a discount, and a push oracle that lags the market can be front-run. Liquity V2 gives redemptions the higher of market and rate while the two are within 1% for wstETH and 2% for rETH.

- **Failure degrades.** A feed that reverts, answers zero or negative, or goes stale must not take liquidations down with it. The branch keeps serving its last good price, reports the outage so new borrowing stops, and keeps serving it on the next call too. Cyfrin's OracleLib reverts on a stale answer and says in its header that the engine freezing "is by design". A CDP with open Troves cannot afford that design.

- **Out of gas is not an outage.** A `try/catch` around the feed call also catches the inner call running out of gas. Without a check that enough gas remains, a precisely gassed call records an oracle failure that never happened, and if the failure is sticky, the branch stays on its last good price for good. Liquity V2 reverts with `InsufficientGasForExternalCall` when less than a 64th of the gas is left after the call.

## The checks

The agent starts with `foundry.toml` and `src/interfaces/IPriceFeed.sol`, with no chain sidecar.
The verifier etches mock contracts at the mainnet addresses of the Chainlink proxies and the LST tokens, listed under Notes, so a script that deploys "against mainnet as is" deploys against them.
It runs the agent's `run()` the way `forge script` would, then drives every price, timestamp and rate through the mocks in [`PriceFeeds.t.sol`](tests/PriceFeeds.t.sol).
The checks read only `fetchPrice()` and `fetchRedemptionPrice()`. They never name a constructor, a library or a threshold, and prices match within 0.1%.
Each test is one idea, and the reward is 1 only when every check passes.

| Check | What it proves | Area |
| --- | --- | --- |
| `compile` | The tests and the agent's contracts compile together | all |
| `test_pricesComeFromTheRightFeeds` | WETH, wstETH and rETH come out in 18-decimal USD from the right feeds and rates: 3000, 3600 and 3300 at ETH/USD 3000, stETH at par, 1.2 stETH per wstETH and 1.1 ETH per rETH, and they follow the feeds when ETH/USD, stETH/USD and the rETH rate move | decimals and composition |
| `test_stalenessFollowsEachFeed` | A price one block past its feed's heartbeat is live and a 72 h old one is not, on every branch that reads a market feed; the age at which rETH/ETH goes stale is at least an hour above the age at which ETH/USD does | staleness |
| `test_lstPriceFollowsTheMarketDownAndTheRateUp` | rETH 4.5% above its rate prices at the rate; rETH 4.5% below prices at the market; wstETH prices at the market with stETH 5% under ETH | LST pricing |
| `test_redemptionPriceProtectsBorrowers` | With both LSTs 0.5% under their rate, the redemption price is at least the borrowing price and matches the rate value; WETH's redemption price equals its price | redemptions |
| `test_brokenFeedKeepsTheBranchLiquidatable` | When ETH/USD reverts, answers 0, answers a negative price or is 73 h old, `fetchPrice` does not revert, reports the outage, returns the last good price, and keeps doing so on the next call and for redemptions; when rETH/ETH alone dies, rETH still serves the last good price or ETH/USD times its rate | failure |
| `test_lowGasCannotFakeAnOutage` | With the ETH/USD feed made as slow as the design's own gas allowance for the oracle call permits, the price moves before each of 49 `fetchPrice` calls with 1.0M to 3.4M gas, and the call after each one returns the new price without an outage flag | gas |

## Why it matters

Decimals and composition have cost money this year.
[rekt's Moonwell write-up](https://rekt.news/moonwell-rekt) describes the cbETH/ETH rate reaching the market as a USD price, "a single missing multiplication", and $1,779,044 of bad debt.
Liquity V2 asserts the feed's `decimals()` in every [price feed constructor](https://github.com/liquity/bold/blob/main/contracts/src/PriceFeeds/MainnetPriceFeedBase.sol).

Staleness thresholds come from the feeds, not from a tutorial.
Chainlink's [feed directory](https://reference-data-directory.vercel.app/feeds-mainnet.json) gives the heartbeat of ETH/USD and stETH/USD as 3600 s and of rETH/ETH and stETH/ETH as 86400 s.
Liquity V2's [deploy script](https://github.com/liquity/bold/blob/main/contracts/script/DeployLiquity2.s.sol) sets 24 h, 24 h and 48 h, and its README's [known issue 5](https://github.com/liquity/bold#5---stale-oracle-price-before-shutdown-triggered) explains why the USD feeds get the lower threshold.
Euler's [ChainlinkOracle](https://github.com/euler-xyz/euler-price-oracle/blob/master/src/adapter/chainlink/ChainlinkOracle.sol) bounds `maxStaleness` between one minute and 72 hours and tells integrators to set it "slightly more than the feed's heartbeat".
Cyfrin's [OracleLib](https://github.com/Cyfrin/foundry-defi-stablecoin-cu/blob/main/src/libraries/OracleLib.sol) is the one-constant, revert-on-stale design.

Getting the staking-rate side wrong is just as expensive as getting the market side wrong.
Aave's [post-mortem of March 10, 2026](https://governance.aave.com/t/post-mortem-exchange-rate-misallignment-on-wsteth-core-and-prime-instances/24269) describes a rate cap set 2.855% under the live wstETH rate and about $26M of liquidations across 34 accounts.
Liquity V2's [RETHPriceFeed](https://github.com/liquity/bold/blob/main/contracts/src/PriceFeeds/RETHPriceFeed.sol) and [WSTETHPriceFeed](https://github.com/liquity/bold/blob/main/contracts/src/PriceFeeds/WSTETHPriceFeed.sol) hold the min, the redemption max and the fallback to ETH/USD times the rate, and the README's [oracle section](https://github.com/liquity/bold#oracles-in-liquity-v2) and [known issue 8](https://github.com/liquity/bold#8---lst-oracle-risks) give the reasoning.

Failure handling and the gas guard are in the same base contract.
Liquity's [MainnetPriceFeedBase](https://github.com/liquity/bold/blob/main/contracts/src/PriceFeeds/MainnetPriceFeedBase.sol) treats a revert, a zero answer or a stale answer as an outage, switches to `lastGoodPrice`, and reverts instead when less than a 64th of the gas remains after the feed call.
Its README's [shutdown section](https://github.com/liquity/bold#collateral-branch-shutdown) lists what keeps working after an oracle failure.
Chainlink's [API reference](https://docs.chain.link/data-feeds/api-reference) marks `answeredInRound` deprecated and says `minAnswer` and `maxAnswer` are "no longer used on most Data Feeds", so neither helps here.

## Notes

- The verifier etches mocks at these mainnet addresses, so a feed built on any of them works. Chainlink proxies: ETH/USD `0x5f4eC3Df9cbd43714FE2740f5E3616155c5b8419`, its SVR variant `0x5147eA642CAEF7BD9c1265AadcA78f997AbB9649` and shared SVR variant `0xd82562bb17557231Cd871e1B2525F3AB8d63D409`, stETH/USD `0xCfE54B5cD566aB89272946F602D76Ea879CAb4a8`, stETH/ETH `0x86392dC19c0b719886221c78AB11eb8Cf5c52812`, the calculated wstETH/USD `0x164b276057258d81941e97B0a900D4C7B358bCe0`, and rETH/ETH `0x536218f9E9Eb48863970252233c8F271f554C2d0`, each with the full `AggregatorV2V3Interface` plus `aggregator()`, `phaseId()`, `minAnswer()` and `maxAnswer()`. Tokens: wstETH `0x7f39C581F595B53c5cb19bD0b3f8dA6c935E2Ca0` with `stEthPerToken`, `tokensPerStEth`, `getStETHByWstETH`, `getWstETHByStETH` and `stETH`; stETH `0xae7ab96520DE3A18E5e111B5EaAb095312D7fE84` with `getPooledEthByShares`, `getSharesByPooledEth`, `getTotalPooledEther` and `getTotalShares`; rETH `0xae78736Cd615f374D3085123A210448E74Fc6393` with `getExchangeRate`, `getEthValue` and `getRethValue`. These are the views Liquity, Aave and Euler read. A feed that reads another address, such as the aggregator behind a proxy, fails as a wrong address would on mainnet. If calibration shows a legitimate source the mocks miss, that is a verifier failure: extend the mocks.
- The three stETH feeds and the calculated wstETH/USD feed always move together and get the same age, so a wstETH feed built on any of them sees the same market and the same staleness.
- Aave prices wstETH and rETH as ETH/USD times a growth-capped staking rate, which ignores a market depeg on purpose. That design fails `test_lstPriceFollowsTheMarketDownAndTheRateUp` here because this is a redeemable CDP whose liquidations and redemptions settle at the market, and the instruction says the LST may trade under its rate.
- The staleness check measures each branch's threshold instead of dictating one. It accepts any threshold above the heartbeat and at or below 72 h, and asks only that rETH/ETH's sit at least an hour above ETH/USD's. Liquity's 24 h and 48 h pass, as does heartbeat plus a few minutes. A branch that never reads its market feed, such as a rate-only rETH feed, is left to the LST check, so one wrong idea fails one check.
- The low-gas check makes the ETH/USD mock burn gas so the window where the inner call runs out and the catch still completes is wide enough to land on. The burn is 3M gas for a design that forwards all its gas, and nine tenths of what a design that caps its oracle call still accepts, found by binary search: a feed slower than the cap looks down to such a design on every call, which is the cap doing its job, not the fault the check is after. The check asserts the consequence, not the guard. A design that records nothing on failure passes, a design that caps the call at a few hundred thousand gas passes because the window does not exist for it, and the real design that fails is Liquity V1's: a sticky `lastGoodPrice` fallback that shuts the branch on a caught failure, ported without the 64th-of-gas check Liquity V2 added.
- A feed that scales an ETH-quoted answer as if it had 8 decimals makes the market value enormous, and a min against the staking rate hides that behind the rate. Such a feed passes the first check and fails the LST check as a rate-only feed would, which is how it would behave on mainnet.
- Not checked: the exact size of the redemption bands, whether a failure is sticky or recovers when the feed does, events, which address a feed reads as long as it is one of the above, and whether a feed still rejects a round whose `answeredInRound` is below `roundId`. Chainlink deprecated that field and current aggregators return it equal to `roundId`, so the mocks do too.
- The solution is a port of Liquity V2's MIT-licensed feeds to the task's interface, with the same 24 h, 24 h and 48 h thresholds. It is one passing design, not the only one.
- The checks run the deploy script the way `forge script` does, with the chain id set to 1 and `PRIVATE_KEY` and `DEPLOYER_PRIVATE_KEY` set, so an ordinary script works unchanged, including one that refuses to run anywhere but mainnet. There is no chain sidecar or RPC dependency.

### Calibration

Two agents ran on the build task, one internet-mode trial each, both paid by a plan.
The open models, OpenCode on GLM 5.3 and on Kimi K3.1, wait for CI after merge, so nothing here says what an open model misses.

| Agent | Checks | Miss |
| --- | --- | --- |
| Claude Code on Opus 5.5 | 6 of 6 | none |
| Codex on GPT-6.1-sol | 6 of 6 | none |

Both trials first scored 0 of 6 against the checks as they stood, and both times the checks were wrong.
Each agent's deploy script refuses to run unless the chain id is 1, which the instruction's "deploy against mainnet as is" invites, and the checks ran it at Foundry's default chain id; they now set the chain id to 1 first.
Codex caps every oracle call at 200,000 gas, so the low-gas check's 3M-gas feed looked down to it; the check now measures how much gas a design lets the feed spend and makes the feed only that slow.
The table is a regrade of both saved workspaces against the fixed checks; the trials themselves have not been rerun.

Claude Code reached mainnet over a public RPC and checked the three feeds' descriptions, decimals and recent round timing with `cast` before writing a line.
It ported Liquity's design with the 64th-of-gas guard, chose 2 h, 2 h and 48 h thresholds, wrote 28 tests plus a fork test, dry-ran its script against mainnet, and fixed only a lint warning along the way.
Codex found the public RPCs blocked and took the heartbeats from Chainlink's, Lido's and Rocket Pool's pages over the web.
It set each threshold at the heartbeat plus five minutes, recomputes the oracle's health on every call instead of keeping a sticky flag, wrote 28 tests plus a fork test it could not run, asked one question about the redemption band and went on with 2% when no answer came, and fixed only lint findings.
Codex's feed also rejects a round whose `answeredInRound` is below `roundId`, the check Chainlink deprecated; the Notes say why nothing here catches it.

The five Concepts quizzes from the same story ran in the vanilla mode on Opus 5.5, and the bare strong model answered all five correctly with the facts the keys rest on, so none of them is yet shown to catch anything.
The open models wait for CI after merge.
