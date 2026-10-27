# Rebalance a Morpho Vaults V2 vault

A curator asks the agent to bring every market under a 25% concentration limit.
The task checks allocations and ordinary depositor access after the move.

## The instruction

> we curate a morpho vaults v2 vault, and almost half of it sits in one market. our risk policy is no market above 25% of the vault. bring it in line by moving funds into the markets we already have, within their caps. deposits and withdrawals must keep working for our users. leave fees, roles, caps and timelocks alone. the vault, that market's id and our wallet are in chain_context.json; the wallet holds the curator and allocator roles. do it on that chain and tell us what you did.

## What it touches

Vault V2 withdraws idle assets first, then pulls from one liquidity adapter and market.
It never searches the other markets.
A solvent vault can reject withdrawals after an allocator moves its liquid assets elsewhere.
The [withdrawal code](https://github.com/morpho-org/vault-v2/blob/425f6b1fb3a1d25083a9515348bd5e7bd3ab9017/src/VaultV2.sol#L766-L818) defines this path.

Each allocation must fit the adapter, collateral, and market caps.
The adapter's live `expectedSupplyAssets` includes interest that the vault's stored `allocation` can omit.
The agent can change allocations and the liquidity adapter and data.
Every cap and all other settings must stay unchanged.
The vault has no submission queue for withdrawals.
Its timelocked submissions must retain their prior executable times, and new submissions must execute or be revoked.

## The checks

The tests read the chain the agent leaves and run depositor transactions on local forks.
RewardKit requires every check to pass.

| Check | What it proves | Area |
| --- | --- | --- |
| `compile` | The tests compile next to the agent's files | all |
| `test_concentrationWithinPolicy` | Every existing market holds at most 25% of live total assets, plus one part per million for interest | concentration |
| `test_withdrawalsStillServed` | A real holder withdraws 10% of starting assets, a small redemption works, and a new deposit works | depositor access |
| `test_fundsStayInvested` | Idle stays at or below 10%, the eight original markets remain, and assets stay intact | investment and preservation |
| `test_nothingElseChanged` | Caps, fees, roles, timelocks, adapters, and pending submissions retain their prior settings | scope |

## Why it matters

Spearbit's [August 2026 public allocator review](https://github.com/morpho-org/vault-v2/blob/main/audits/2026-08-13-blue-public-allocator-spearbit.pdf), finding 5.1.4, describes allocations stripping withdrawal liquidity.
ChainSecurity's [September 2025 review](https://github.com/morpho-org/vault-v2/blob/main/audits/2025-09-15-chainsecurity.pdf), note 8.5, describes the same withdrawal constraint.
Users then need `forceDeallocate`, which can charge a penalty.
Morpho's [liquidity guide](https://docs.morpho.org/curate/concepts/liquidity) explains the allocator's role in keeping withdrawals available.

## Notes

- The fork pins Ethereum block 26,256,000, dated October 23, 2026 at 14:43:47 UTC.
- Setup transfers curator authority and adds the agent as allocator. It changes no caps or market liquidity.
- Only `MAINNET_RPC_URL` enters the chain sidecar. The agent gets the filtered RPC and its wallet key.
- At the pinned block, total assets are 112,074,335.150878 USDC, with zero idle assets.
- At that size, a 10% withdrawal is 11,207,433.515087 USDC. Setup records 10% of the live balance after the role handover.
- The real holder `0x087e2aac2e2457a5107700a58543e35ff63391b4` holds about 21.563M USDC in shares.
- The withdrawal tests a partial exit by an existing holder without adding shares or liquidity first.
- "Deposits and withdrawals must keep working for our users" is read as that holder's 10% withdrawal, because a rebalance that strips liquidity is the risk here. The market exit task reads the same words as a fresh round trip, since its ask lets the funds sit idle.
- The small redemption covers about 1,000 USDC. A separate stranger deposits and redeems 1,000 USDC.
- Idle can reach 10%, or about 11.207M USDC. At least 90% must remain invested in the original markets.
- This allows a cash buffer for withdrawals without accepting a rebalance that parks the released funds in idle.
- Total and directly held assets allow ten USDC base units of rounding loss and 0.01% interest growth.
- Concentration allows one part per million of total assets above 25%, about 112 USDC at the starting size.
- The solution targets 24.9%, invests the released funds in existing markets, and selects a route with enough withdrawal liquidity.

Measured market balances at the pinned block follow. Liquidity is Morpho supply assets minus borrow assets before interest accrual.

| Market id prefix | Collateral | Vault USDC | Available USDC | Market absolute cap USDC |
| --- | --- | ---: | ---: | ---: |
| `0x85252bb8` | weETH | 25,723,681.883561 | 3,941,615.679542 | 100,000,000 |
| `0x64d65c9a` | cbBTC | 52,786,880.855432 | 34,028,495.220411 | 1,000,000,000 |
| `0x7e585a93` | wstETH | 7,260,508.392776 | 1,246,806.063363 | 200,000,000 |
| `0x09dc9e7e` | WBTC | 837,103.095793 | 154,179.008491 | 200,000,000 |
| `0xbc99de6a` | cbBTC | 175,144.321260 | 102,657.424568 | 1,000,000,000 |
| `0x94b823e6` | WETH | 2,053,775.033386 | 966,051.834986 | 200,000,000 |
| `0xb323495f` | wstETH | 1,162,961.743931 | 3,228,844.521907 | 200,000,000 |
| `0x3a85e619` | WBTC | 22,074,279.824739 | 12,983,981.290639 | 200,000,000 |

All relative caps are 100%.
The adapter absolute cap is 1,000,000,000,000 USDC.
Collateral caps are 100M for weETH, 1B for cbBTC, and 200M each for wstETH, WBTC, and WETH.
No setup cap raise is needed.

A naive rebalance lowers cbBTC to 24.9% and moves all released assets to WETH without changing the route.
It meets concentration, investment, and scope checks.
It leaves about 9.148M USDC available on the cbBTC route, so the 11.207M withdrawal reverts with insufficient liquidity.

The solution spreads 19.5M over five existing markets within the 25% policy, leaves about 5.4M idle, and changes the route to the existing WBTC market.
That market then has about 18.5M USDC available, and idle pays out first, so the 11.207M withdrawal has about 12M of room.
