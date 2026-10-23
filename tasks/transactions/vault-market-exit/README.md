# Exit a Morpho vault market

A vault team no longer trusts one market's oracle and asks the agent to move its depositors fully out.
The task checks that the exit preserves assets and stops that market from affecting the vault's value.

## The instruction

```text
we curate the vault in chain_context.json on morpho. one of its markets, the one whose id is also in chain_context.json, has an oracle we no longer trust after yesterday's incident. we want our depositors fully out of that market, for good. move whatever's there into the vault's other markets or leave it idle, your call, and don't change anything else about the vault. our wallet in chain_context.json holds the curator and allocator roles. please do it on that chain and tell us what you did.
```

## What it touches

A zero cap limits new allocations, but leaves existing supply shares and both queues in place.
An allocator must move the full position into another enabled market before removing it from the withdraw queue.
Removing a market without waiting requires a zero cap, no pending cap, and zero supply shares.

Morpho Blue lets any address supply on behalf of the vault.
The cap cannot refuse that supply.
MetaMorpho v1.1 counts positions on the withdraw queue when it computes assets, so an empty listed market still affects depositor value.
The [vault source](https://github.com/morpho-org/metamorpho-v1.1/blob/main/src/MetaMorphoV1_1.sol) defines these rules.

## The checks

Setup gives a fresh wallet the curator and allocator roles and 10 ETH on the fork.
The chain context gives the agent its address, key, vault, and market id.
The tests read the final chain state, then supply USDC from a stranger with the vault as receiver.

| Check | What it proves | Area |
| --- | --- | --- |
| `compile` | The tests compile next to the agent's files | all |
| `test_vaultIsOutForGood` | The market has no vault shares, cap, pending cap, or queue entry; assets and unrelated vault settings stay intact | full exit |
| `test_strangerSupplyOnBehalfChangesNothing` | A stranger can supply into the old market without changing the vault's total assets | donation isolation |

## Why it matters

[Lazy Summer's July 6, 2026 retrospective](https://forum.summer.fi/t/lazy-summer-protocol-exploit-july-6-2026-ba-labs-risk-curator-retrospective/856) describes a loss through a market with a zero cap that remained in the vault.
[BlockSec's Silo soUSDC incident account](https://blocksec.com/blog/weekly-web3-security-incident-roundup-mar-30-apr-5-2026) describes an April 3 deposit with the vault as receiver after its cap reached zero.
The [Resolv incident account](https://rekt.news/resolv-labs-rekt) also describes supply on behalf of vaults after curators lowered caps.
Morpho's [vault documentation](https://docs.morpho.org/learn/concepts/vault/) warns that caps limit reallocations, while donations can still reach a listed market.

## Notes

- The fork pins Ethereum block 26,256,000, dated October 23, 2026 at 14:43:47 UTC. The RPC served contract state there during authoring.
- The vault is Safe x Steakhouse USDC, `0xbEeFCe6c76C7D7A8066562Fe9FF0e343a52dD92F`. The [mainnet v1.1 factory](https://docs.morpho.org/developers/contracts/addresses/) at `0x1897A8997241C1cD4bD0698647e4EB7213535c24` recognizes it. It has four enabled markets and uses USDC.
- The exit market is `0x64d65c9a2d91c36d56fbc42d69e979335320169b3df63bf92789e2c8883fcc64`, backed by cbBTC. Its vault position is about 1,662,384 USDC and its available liquidity is about 34,028,495 USDC.
- The solution moves all proceeds into the enabled USDC idle market, `0x54efdee08e272e929034a8f26f7ca34b1ebe364b275391169b28c6d7db24dbc8`. Its cap is 1,000,000,000,000 USDC and its oracle, collateral, and interest model are zero.
- The asset check permits a loss of ten USDC base units and a gain of 0.01 percent for accrued interest. It also checks actual market assets because v1.1 can carry lost assets in `totalAssets`.
- This task needs `MAINNET_RPC_URL`. The agent uses the filtered sidecar RPC and signs with its own key.
