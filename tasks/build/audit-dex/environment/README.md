# Kestrel

Kestrel is a constant-product exchange. Every pool lives in one contract, `KestrelVault`, which holds the tokens of all pools together. Users trade and provide liquidity through `KestrelRouter`.

## How it works

- **Pools.** A pool is a token pair at a fee tier: 0.05%, 0.30%, or 1.00% at launch. Anyone can create a pool. Pricing is `x * y = k` with the fee taken from the input, as in Uniswap V2.
- **Paying the vault.** The vault does not pull tokens. A caller delivers tokens to the vault and then calls `addLiquidity` or `swap` in the same transaction. The vault credits the caller with the tokens it received since its last accounting. The router does both steps for users.
- **Multi-hop swaps.** The router sends each hop's output back into the vault, which credits it as the input of the next hop. Tokens never leave the vault between hops.
- **Liquidity.** Liquidity providers get pool shares, held inside the vault per pool. The first deposit locks 1,000 shares forever. Deposits beyond the pool's ratio stay in the pool. To remove liquidity through the router, a provider first approves the router as an operator with `setOperator`.
- **Fees.** The whole swap fee stays in the pool for liquidity providers, except a protocol share (20% of the fee at launch, at most 25%). The protocol share accrues per token in the vault. Anyone can call `collectProtocolFees` to send accrued fees to the fee recipient; we run a keeper that calls it daily.
- **Skim.** Tokens sent to the vault outside a swap or deposit can be taken out by anyone with `skim`.

## What we promise

- A trader receives the constant-product output, after the pool fee, for exactly the tokens they delivered.
- A liquidity provider receives shares in proportion to what they deposited, and can always withdraw their pro-rata share of the reserves.
- The protocol's revenue is the protocol share of the swap fee and nothing more.
- Pools are isolated: activity in one pool never changes the price or reserves of another.

## Roles and trust

| Role | Trust | Powers |
| --- | --- | --- |
| Owner (team multisig) | Trusted | Enable or disable fee tiers, set the protocol share up to 25% of the fee, set the fee recipient, transfer ownership |
| Fee recipient (treasury) | Trusted | Receives protocol fees |
| Keeper | Untrusted | Calls `collectProtocolFees`, which anyone may call |
| Users, liquidity providers, pool creators | Untrusted | Everything else |

## Scope

| File | Lines |
| --- | --- |
| `src/KestrelVault.sol` | 270 |
| `src/KestrelRouter.sol` | 174 |
| `src/libraries/KestrelMath.sol` | 51 |
| `src/libraries/SafeTransfer.sol` | 24 |
| `src/interfaces/IKestrelVault.sol` | 57 |
| `src/interfaces/IERC20.sol` | 14 |

Out of scope: `test/`.

Kestrel launches on Ethereum mainnet and Base. Supported tokens are standard ERC-20s with 6 to 18 decimals. Fee-on-transfer, rebasing, and other balance-changing tokens are not supported.

## Known issues

These are known and accepted, and will not be rewarded:

1. Tokens sent directly to the vault, outside a router call or a contract that delivers and calls in one transaction, can be taken by anyone through `skim`, or credited to the next caller's swap or deposit. Integrators must deliver and call in one transaction.
2. Pool reserves move within a block and can be manipulated with a flash loan. Kestrel pools must not be used as price oracles.
3. Swaps through the router are open to sandwich attacks when users set loose `amountOutMin` values. The frontend sets 0.5% by default.

## Build and test

```sh
forge build
forge test
```
