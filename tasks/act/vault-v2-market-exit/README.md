# Exit a Morpho Vaults V2 market

A vault team asks the agent to exit one market after an oracle incident.
The task checks that pending cap raises cannot reopen it and that depositors can still use the vault.

## The instruction

> we curate a morpho vaults v2 vault, and one of its markets has an oracle we no longer trust after yesterday's incident. get our depositors fully out of that market, for good: nobody should be able to put the vault back in. move the funds to the other markets or leave them idle, your call. deposits and withdrawals must keep working, and nothing else about the vault changes. the vault, the market id and our wallet are in chain_context.json; the wallet holds the curator and allocator roles. do it on that chain and tell us what you did.

## What it touches

V2 gives each market an absolute cap and a relative cap under an adapter-specific id.
The collateral id can cover several markets, so lowering its caps changes unrelated markets too.
Unlike MetaMorpho v1.1, a cap decrease leaves pending increases executable.
The curator must revoke the exact calldata for both pending raises.
The [cap setters](https://github.com/morpho-org/vault-v2/blob/425f6b1fb3a1d25083a9515348bd5e7bd3ab9017/src/VaultV2.sol#L516-L554) and [timelock functions](https://github.com/morpho-org/vault-v2/blob/425f6b1fb3a1d25083a9515348bd5e7bd3ab9017/src/VaultV2.sol#L342-L377) define these rules.

V2's [deallocate function](https://github.com/morpho-org/vault-v2/blob/425f6b1fb3a1d25083a9515348bd5e7bd3ab9017/src/VaultV2.sol#L593-L618) takes an asset delta.
The stored allocation can lag interest, so it cannot name the full withdrawal amount.
The [adapter](https://github.com/morpho-org/vault-v2/blob/425f6b1fb3a1d25083a9515348bd5e7bd3ab9017/src/adapters/MorphoMarketV1AdapterV2.sol#L194-L256) can leave supply-share dust worth nothing after a full deallocation.

The checks measure "out" by zero expected supply assets and absence from the adapter's market list.
They read Morpho's actual position and accept leftover supply shares only when they are worth zero base units and the adapter no longer lists the market.
Caps and pending raises must be exactly zero, and the liquidity route must no longer point at the market.

Deposits use one liquidity route and enforce its caps.
Keeping the route on the exited market makes deposits revert with `ZeroAbsoluteCap`.
Withdrawals use idle assets and that same route, with no queue of fallback markets.
The [deposit and withdrawal code](https://github.com/morpho-org/vault-v2/blob/425f6b1fb3a1d25083a9515348bd5e7bd3ab9017/src/VaultV2.sol#L766-L818) defines this behavior.

## The checks

Setup hands a fresh wallet the curator and allocator roles without removing the existing allocators or sentinel.
It leaves two pending cap raises, keeps the unsafe deposit route, and records the prior settings privately.
The tests read the chain the agent leaves and run depositor and stranger transactions on local forks.

| Check | What it proves | Area |
| --- | --- | --- |
| `compile` | The tests compile next to the agent's files | all |
| `test_vaultIsOutForGood` | The market has no valuable supply shares, listing, caps, pending raises, or liquidity route | full exit |
| `test_strangerCannotReopenIt` | Dust has zero value before the time jump, and strangers cannot execute mature raises or add supply shares | pending raises and public allocation |
| `test_depositorsStillServed` | A stranger can deposit and withdraw USDC without losing more than one base unit, and the exit preserves vault assets | depositor access |
| `test_nothingElseChanged` | Other settings and per-market assets stay intact, and no new vault or adapter submission remains pending | scope and asset preservation |

## Why it matters

Morpho [launched Vaults V2 on Ethereum on September 29, 2025](https://morpho.org/blog/morpho-vaults-v2-a-new-standard-for-asset-curation).
Gauntlet USDC Prime V2 followed on September 30 at block 23,479,188.
These vaults first wrapped V1 vaults and later moved to direct market adapters.
The [Steakhouse migration announcement](https://forum.morpho.org/t/steakhouse-vault-v2-simplification/2235), dated April 15, 2026, describes that change.
Its [April 9 depositor guide](https://kitchen.steakhouse.financial/p/morpho-v2-is-the-new-standard) also describes upgrades from V1 to V2.

Mainnet adapter events show the migration dates.

- [steakUSDC V2](https://etherscan.io/address/0xbeef088055857739C12CD3765F20b7679Def0f51#events): the direct adapter arrived April 20, 2026 at block 24,923,943. Its route moved April 23 at block 24,942,643, and its V1 adapter left May 1 at block 24,998,920.
- [Gauntlet USDC Prime V2](https://etherscan.io/address/0x8c106EEDAd96553e64287A5A6839c3Cc78afA3D0#events) added its direct adapter April 24 and removed its wrapper June 2.
- [Sentora RLUSD V2](https://etherscan.io/address/0x6dC58a0FdfC8D694e571DC59B9A52EEEa780E6bf#events) added its direct adapter April 29 and removed its V1.1 wrapper July 3.

An exit procedure copied from V1.1 misses pending V2 raises and its single deposit route.
Morpho's [emergency guide](https://docs.morpho.org/curate/tutorials-v2/emergency/) calls for revoking pending raises before lowering caps and moving funds.

## Notes

- The fork pins Ethereum block 26,256,000, dated October 23, 2026 at 14:43:47 UTC.
- The vault is steakUSDC V2, `0xbeef088055857739C12CD3765F20b7679Def0f51`, with one adapter and eight markets.
- The exit market is cbBTC/USDC at 86% LLTV, `0x64d65c9a2d91c36d56fbc42d69e979335320169b3df63bf92789e2c8883fcc64`.
- Its position exceeds free market liquidity at the pinned block. Setup supplies the shortfall plus 2,000,000 USDC from a funded mainnet supplier.
- Both raises mature during the stranger check. The relative raise restores the existing 100% cap, which the contract accepts.
- The stranger check measures dust value before the time jump, then requires supply shares to stay unchanged.
- New vault and adapter submissions must execute or be revoked. The exit check requires revocation of setup's two pending raises.
- Each other market must retain at least its recorded supply assets minus one USDC base unit.
- The exit market's funds can go to idle or another market, within the total asset bounds.
- The asset checks permit ten USDC base units of rounding loss and 0.01 percent of interest growth.
- This task needs `MAINNET_RPC_URL`. The agent gets only the filtered chain RPC and its own wallet key.
