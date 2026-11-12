# VRF raffle

A community raffles its one-of-one NFT: 0.01 ETH tickets for seven days, one winner from Chainlink VRF 2.5, the pot to the treasury, and refunds if fewer than 100 tickets sell.
The message is the one any community sends: a price, a deadline, a draw button, a settle button, and a page that talks to the raffle through an interface.
Hidden Forge tests play the oracle, and check the things a VRF consumer that holds other people's money has to get right, none of which the message spells out.

Randomness is where the textbook and the production contract part ways.
The textbook raffle picks the winner and pushes the payout inside the VRF callback, and it works until the winner is a contract that cannot receive, or the oracle never answers.
Chainlink's coordinator forgets a request before it calls the consumer and never retries, so a callback that reverts kills the round with everyone's ETH inside.
This task checks the gap between a raffle that draws and a raffle the community can safely sell tickets for.

## The instruction

> we're raffling off our community's 1/1 NFT. tickets are 0.01 ETH each, as many as you like per
> wallet, and sales run for seven days from deploy. the draw has to use chainlink VRF 2.5, we have a
> funded subscription. our page has a draw button for when sales close and a settle button for when
> the randomness is in, and anyone can press them: settle names the winner and sends the whole pot
> to our treasury without us doing anything, and the winner collects the NFT from the page. if fewer
> than 100 tickets sell the raffle is off and everyone gets their ETH back. it has to run without us:
> nobody should need us to get their money or the NFT, and we expect a few thousand buyers. the page
> talks to it through src/interfaces/IRaffle.sol. put the raffle in src/Raffle.sol as Raffle, and a
> deploy script in script/Deploy.s.sol whose run(coordinator, subId, keyHash, nft, tokenId, treasury)
> deploys it and returns its address. we'll run it once from the wallet that holds the NFT and owns
> the subscription, so leave the raffle ready to go. we're on foundry with solidity 0.8.30, going to
> mainnet.

## What it touches

The instruction leaves out six things. Each has a real finding or an adopted pattern behind it.

- **The callback stores and nothing else.** [VRFCoordinatorV2_5](https://github.com/smartcontractkit/chainlink-evm/blob/contracts-v1.5.0/contracts/src/v0.8/vrf/dev/VRFCoordinatorV2_5.sol#L486-L487) deletes the request's commitment before it calls the consumer, and the fulfilment's `success` flag is the only record of a callback that reverted. The [textbook raffle](https://github.com/Cyfrin/foundry-smart-contract-lottery-cu/blob/main/src/Raffle.sol#L172-L179) takes the word modulo the players and pushes the whole balance to the winner inside `fulfillRandomWords`. A winner that is a contract without `onERC721Received`, or one that rejects ETH, reverts that callback, and the raffle is dead. Pashov's second BearCave review (M-01) and the May RipIt review (M-01, a prize sender that leaves the NFTs stuck when one send fails) say the same thing: cache the randomness, act in a separate call. The instruction's settle button is that separate call, and the check makes the only buyer a contract that takes neither ETH nor NFTs.

- **A silent oracle must not strand the pot, and nobody may ask twice.** Chainlink's [security page](https://docs.chain.link/vrf/v2-5/security) calls any re-request or cancellation of randomness an incorrect use, because the oracle can withhold an answer until a re-request gives one it likes. Pashov rated a public re-request Critical in the first BearCave review (C-04). An unfunded request [expires after 24 hours](https://docs.chain.link/vrf/v2-5/overview/subscription), and nothing moves on its own. PoolTogether's [DrawManager](https://github.com/GenerationSoftware/pt-v5-draw-manager/blob/main/src/DrawManager.sol) bounds retries and rejects a stale request. So the raffle has to refuse a second draw while one is pending and after a result, and still give the buyers a way out after a long silence: refunds, or one fresh request whose stale predecessor cannot decide the raffle. A timeout that refunds is safe where a casual re-request is not, because it gives nobody a choice between outcomes. The fulfilment comes only through the coordinator, and whoever can hold it back, the oracle operator or the subscription owner by cancelling or draining the subscription, can only turn the raffle into a refund, never pick the winner.

- **The draw is one request at the right time.** Entries close when the request goes out. In the second BearCave review (H-01) a mint front-ran the fulfilment, and the number of entries the callback read at that moment changed the winner; the April RipIt review's M-06 is the same finding. The check requests the draw and then tries to buy.

- **The randomness is Chainlink's, under mainnet's limits.** The mock takes any parameters. Mainnet's coordinator [rejects](https://docs.chain.link/vrf/v2-5/supported-networks) a callback gas limit above 2,500,000 and fewer than 3 confirmations, so a raffle tested only against the mock can be undrawable once deployed. The May RipIt review's L-13 flagged confirmations below Chainlink's minimum, and the April review's L-20 a count too low for the chain. Only the coordinator may fulfil, which `VRFConsumerBaseV2Plus` enforces and a hand-rolled consumer has to. A winner named before the fulfilment comes from the block, not the oracle.

- **Thousands of buyers.** The callback runs under its own gas limit, at most 2,500,000 on mainnet, and a loop over buyers to find the weighted winner runs out of gas there. Moved to settle, the same loop is bounded by [EIP-7825](https://eips.ethereum.org/EIPS/eip-7825), which caps one mainnet transaction at 16,777,216 gas since Fusaka. With 5,000 buyers and cold storage, a loop that reads a buyer and a count per step costs 23.8M gas and cannot be mined; a binary search over purchases costs 109k.

- **The deploy script does two things the message only implies.** The raffle must be added as a consumer of the subscription, which only the subscription's owner can do, or `requestRandomWords` reverts with `InvalidConsumer` on the mock and on mainnet alike. And the NFT must move into the raffle before the first ticket sells. The script runs from the wallet that owns both, so it can do both, and the instruction says to leave the raffle ready. A script that only deploys leaves a raffle that sells tickets for a prize it does not hold and cannot draw.

`IRaffle` fixes the page's surface, including `claimPrize` and `claimRefund`, so the prize and the refunds are pulled by design. What the interface leaves open is everything above: what the callback does, when the raffle gives up on the oracle, whether a second draw is possible, and how the winner is found.

## The checks

The agent starts with `IRaffle`, a `foundry.toml`, OpenZeppelin 5.7.0 and 4.9.6, and `@chainlink/contracts` 1.5.0 in `lib/`.
The verifier deploys Chainlink's `VRFCoordinatorV2_5Mock`, creates a subscription owned by the deploy wallet and funds it in LINK and in ETH, mints the prize NFT to that wallet, and runs the agent's script the way `forge script` would.
It then sells tickets, moves the clock, and plays the oracle through `fulfillRandomWordsWithOverride` under the raffle's own callback gas limit, reading the callback's `success` flag from the coordinator's event.
Before each fulfilment and each settlement it marks the raffle's storage cold, as a fresh mainnet transaction would find it.
It reads the raffle only through `IRaffle`, the NFT's owner, and balances, so any winner formula and any state machine behind the interface can pass.
Each test is one idea, and the reward is 1 only when every check passes.

| Check | What it proves | Area |
| --- | --- | --- |
| `compile` | The tests and the agent's contracts compile together | all |
| `test_oneDrawAtTheRightTime` | No request before the deadline; one request at the draw; no ticket sold after it; no second request while pending or after the result | timing |
| `test_theWinnerComesFromChainlink` | The request uses our subscription with mainnet-valid confirmations and callback gas; no winner before the fulfilment; a stranger's words count for nothing; five words give differing winners; the winner holds a ticket and gets the NFT; the treasury gets the whole pot | randomness |
| `test_aHostileWinnerCannotBlockTheRound` | With every ticket held by a contract that rejects ETH and NFTs, the callback succeeds, the treasury is paid, and the NFT is not lost | callback |
| `test_tooFewTicketsRefundsEveryone` | With 99 tickets nothing is requested, no winner is named, each buyer gets back exactly what they paid, once, and nobody else gets anything | refunds |
| `test_aSilentOracleDoesNotStrandThePot` | Nothing gives up within an hour of the request; after thirty days every buyer can be refunded, or one fresh request can be made and the stale one cannot decide the raffle | oracle silence |
| `test_thousandsOfBuyersStillDraw` | With 5,000 buyers the callback succeeds under its own gas limit, settlement fits in one 16,777,216-gas transaction, and the winner holds a ticket | scale |

A score of 0 says the agent carried some of these ideas but not all. The per-check record says which, and that record is what the board learns from.

## Why it matters

A reverting callback has no second chance.
Chainlink's [security page](https://docs.chain.link/vrf/v2-5/security) says the service will not call `fulfillRandomWords` a second time, and the [coordinator](https://github.com/smartcontractkit/chainlink-evm/blob/contracts-v1.5.0/contracts/src/v0.8/vrf/dev/VRFCoordinatorV2_5.sol#L486-L487) deletes the request before the call.
Pashov's [second BearCave review](https://github.com/pashov/audits/blob/master/solo/md/BearCave-second-security-review.md) found a callback that could run out of gas and told the team to cache the randomness and let an account finish the job; the [May RipIt review](https://github.com/pashov/audits/blob/master/team/md/RipIt-security-review_2025-05-10.md) found NFTs stuck for good when `sendNFTs()` failed (M-01) and an open that went through on an empty cards array (L-12), and the [April RipIt review](https://github.com/pashov/audits/blob/master/team/md/RipIt-security-review_2025-04-25.md) found a lottery still taking inputs after its randomness request (M-06).
OpenZeppelin removed `PullPayment` in [5.0.0](https://github.com/OpenZeppelin/openzeppelin-contracts/blob/master/CHANGELOG.md), so the pull pattern is the developer's to write; Nouns' auction house [pushes with 30,000 gas and falls back to WETH](https://github.com/nounsDAO/nouns-monorepo/blob/master/packages/nouns-contracts/contracts/NounsAuctionHouseV3.sol) for the same reason.

Re-requesting randomness hands the oracle a choice.
The [first BearCave review](https://github.com/pashov/audits/blob/master/solo/md/BearCave-security-review.md) rated a public re-request Critical, and Chainlink's page names re-requests and cancellations as incorrect use.
PoolTogether's [DrawManager](https://github.com/GenerationSoftware/pt-v5-draw-manager/blob/main/src/DrawManager.sol) retries only a request its oracle reports as failed, a bounded number of times, and rejects a stale one.
The other half of the same problem is a pot nobody can reach: an unfunded request [expires after 24 hours](https://docs.chain.link/vrf/v2-5/overview/subscription), and a raffle with no exit holds the ETH forever.

Entries after the request change the winner.
The second BearCave review's H-01 and the April RipIt review's M-06 both found inputs accepted after the randomness was requested, and Chainlink's page says to stop accepting inputs that affect the outcome before requesting.

Limits that the mock does not enforce bite on mainnet.
The [supported networks](https://docs.chain.link/vrf/v2-5/supported-networks) page sets the 2,500,000 callback gas limit and the 3-confirmation minimum, and [EIP-7825](https://eips.ethereum.org/EIPS/eip-7825) caps a transaction at 16,777,216 gas since Fusaka, so a settlement loop sized for a test with fifty buyers fails with five thousand.

## Notes

- Every check has a design behind it that fails it. Letting `draw()` through while a request is pending fails `test_oneDrawAtTheRightTime` with `a second randomness request went out while the first was pending`. Naming the winner from `blockhash` without waiting fails `test_theWinnerComesFromChainlink` with `a winner was named before the randomness arrived`; one confirmation fails it with `fewer confirmations than mainnet's minimum of 3`. Pushing the NFT with `safeTransferFrom` inside the callback fails `test_aHostileWinnerCannotBlockTheRound`. Requesting randomness with 99 tickets fails `test_tooFewTicketsRefundsEveryone`. Removing the timeout fails `test_aSilentOracleDoesNotStrandThePot` with `the pot is stranded`. Finding the winner with a loop inside the callback fails `test_thousandsOfBuyersStillDraw` under the callback gas limit; the same loop in `settle()` reading two slots per buyer fails it with 23.8M gas against the 16,777,216 cap.
- To prove the tests catch a wrong answer, delete the line in `solve.sh` that calls `_callOff()` when the oracle has been silent for `ORACLE_TIMEOUT`, and run the free check. The oracle run fails `test_aSilentOracleDoesNotStrandThePot` with `after thirty days of silence nobody can get a refund and nobody can draw again: the pot is stranded`. Put it back.
- One agent built exactly the design the silence check exists for. Codex on GPT-6.1-sol read Chainlink's warning against re-requests and forbade every exit: its own README says a pending request "cannot be cancelled, timed out into refunds, or rerolled", and its test `testPendingRandomnessCannotBeCancelledOrRerolledAfterDelay` locks that in. It asked for 200 confirmations, the mainnet maximum, so every draw waits about forty minutes, and if the fulfilment never comes the pot and the NFT stay in the contract forever. The instruction's "it has to run without us" is the sentence that breaks: a raffle nobody can unwind needs the community, or Chainlink, to come back. The refund exit it refused is the safe one, as the silent-oracle bullet above explains, and the check failed it with `the pot is stranded`.
- The checks accept push or pull for the prize: `claimPrize` is called only when the NFT has not already reached the winner. `settle()` is pressed only when the winner or the pot is still missing, so a raffle that does both in the callback passes too. Refunds may open by time alone, through `draw()`, or through `settle()`. The winner formula is never read; the randomness check needs only that five different words do not all give the same winner.
- The silence thresholds are a judgment. A raffle that lets anyone refund or re-request within an hour of the request fails, and one that still has no exit after thirty days fails. Chainlink's 24-hour expiry sits between them. A re-request design must ignore the fulfilment of the request it gave up on; one that takes whichever answer arrives first fails, by Chainlink's rule and PoolTogether's.
- The scale check uses 5,000 single-ticket buyers and a word that lands on the last ticket under `word % ticketsSold`, so a scan over buyers runs its full length. A scan that reads one slot per buyer costs 12.5M gas cold and passes the cap; a loop that reads a buyer and a count per step costs 23.8M and fails. A design that hashes the word before the modulo lands somewhere random, and a scan there may pass by luck. Both scans fail inside the callback.
- The verifier compiles its own copies of the mock and its imports from `tests/chainlink/`, so what the agent does to `lib/` cannot break the checks. `tests/chainlink/NOTICE.md` records the version, the hash and the one import that was made relative.
- The mock's gas accounting is not mainnet's, and the test never sends real LINK. The subscription is funded in both LINK and ETH so either `nativePayment` setting works.
- There is no chain sidecar or RPC dependency. The checks run the deploy script the way `forge script` does and set `PRIVATE_KEY`, `DEPLOYER_PRIVATE_KEY` and `FOUNDRY_SENDER`, so an ordinary script works unchanged.

### Calibration

Only two agents ran on the build task, one internet-mode trial each, both paid by a plan.
The open models, OpenCode on GLM 5.3 and on Kimi K3.1, were skipped, so nothing here says what an open model misses.

| Agent | Checks | Miss |
| --- | --- | --- |
| Claude Code on Opus 5.5 | 7 of 7 | none |
| Codex on GPT-6.1-sol | 6 of 7 | `test_aSilentOracleDoesNotStrandThePot`, by design |

Claude Code passed after real reading and testing, and never had to fix the contract.
It read `IRaffle`, the Chainlink consumer base, the coordinator's request and fulfilment code and the mock, wrote 18 tests of its own, including a fuzz over ticket ranges, a hostile treasury, a silent oracle and 5,000 purchases, and broadcast its deploy script on a local chain, fixing three mistakes in its own harness on the way.
Its raffle has no owner at all, never re-requests, refunds after two days of silence and finds the winner by binary search.
Codex read the same sources plus Chainlink's security page over the web, wrote 40 tests of its own and found `vm.cool` to measure settlement cold, and missed one check for the reason the Notes bullet above describes.
Its two fixes along the way were in its tests, not the contract.

The four Concepts quizzes from the same story ran in the vanilla mode on Opus 5.5, and the bare strong model answered all four correctly, with the same facts the keys rest on, so none of them is yet shown to catch anything.
The Arbitrum `prevrandao` quiz needed a rewording first: its original instruction opened with "our dice game mixes block.prevrandao into its seed", which a refusal classifier read as tampering with game randomness, so two attempts came back with no text; the question now asks the bare value and the dice game stays in that quiz's README.
The open models wait for CI after merge.
