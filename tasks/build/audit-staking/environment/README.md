# Ballast Staking

Ballast is a lending protocol. Ballast Staking lets BLST holders back the Ballast lending markets: stakers earn most of the protocol's fees, and in return their stake can be slashed to cover bad debt that a market cannot absorb.

## How it works

**Staking.** A staker deposits BLST into `BallastStaking` and gets shares. A position is worth its share of the BLST staked in the pool. Rewards raise the value of each share and slashes lower it.

**Rewards.** Ballast markets send their fees, in BLST, to `FeeRouter`. Anyone can call `FeeRouter.distribute()`, which sends 80% to `BallastStaking` and the rest to the treasury. BLST that arrives at `BallastStaking` outside of staking is picked up by `harvest()` and streamed to stakers over the next 7 days, together with whatever is still streaming. Streaming stops someone from staking just before a fee run and leaving with part of it. `harvest()` is open to anyone, so a keeper or any staker can start a stream.

**Leaving.** A staker calls `requestWithdrawal(shares)`. The shares leave the pool, their BLST value at that moment is recorded, and the staker can claim it with `claimWithdrawal` once the cooldown (10 days by default) has passed. Queued BLST earns no rewards. A staker can change their mind with `cancelWithdrawal`, which puts the BLST back in the pool at the current share price.

**Slashing.** When a market is left with bad debt, governance proposes a slash in `ShortfallModule`: an amount of BLST and the market that receives it. The proposal is public and waits a delay (2 days by default). During the delay the guardian can veto it. After the delay anyone can execute it within a 3-day window. A single slash can take at most 30% of the stake. If the stake is smaller than the proposal expects, the slash takes the 30% maximum instead.

## What the protocol promises

1. A queued withdrawal can always be claimed in full once its cooldown ends. Nothing an outside caller does can stop a staker from getting out.
2. Stakers share rewards and slashes in proportion to their stake.
3. The cooldown is there so that stakers cannot leave the moment a loss becomes likely. Stake waiting in the cooldown queue still backs the markets until it is claimed: a slash cuts queued withdrawals by the same percentage as active stake.
4. BLST held by `BallastStaking` always covers what stakers and queued withdrawals are owed.

## Roles and trust

| Role | Who | Can |
| --- | --- | --- |
| Owner of `BallastStaking` | Governance timelock | set the slasher, set the cooldown (up to 30 days), pause new stake and cancellations, transfer ownership |
| Slasher | `ShortfallModule` | call `slash` |
| Governance | Governance timelock | propose slashes, set the delay (1 to 7 days), the guardian, and governance |
| Guardian | Security council multisig | veto a proposed slash |
| Owner of `FeeRouter` | Governance timelock | set the stakers' share (50% to 100%) and the treasury |
| Anyone | | stake, queue, cancel and claim their own withdrawals, call `harvest`, `distribute`, and `executeSlash` |

Governance, the guardian, and the treasury are trusted. Stakers, keepers, and anyone calling the open functions are not.

BLST is a standard 18-decimal ERC-20 with no fees on transfer, no rebasing, and no hooks.

## Scope

In scope:

```text
src/BallastStaking.sol
src/ShortfallModule.sol
src/FeeRouter.sol
src/libraries/SafeTransfer.sol
src/interfaces/IERC20.sol
```

Out of scope: the Ballast lending markets, the BLST token, and the governance timelock. The tests under `test/` are not in scope.

The contracts will be deployed on Ethereum mainnet. Build and test with `forge build` and `forge test` (Solidity 0.8.30).

## Known issues

These are known and accepted. Please don't report them.

- If every staker leaves while rewards are still streaming, the rewards that vest while the pool is empty go to the next staker.
- `harvest()` divides the stream by 7 days and rounds down, so up to a few hundred thousand wei per harvest stays in the contract and is picked up by the next harvest.
- Governance can slash 30% at a time and can propose several slashes in a row. Stakers rely on governance and the guardian not to abuse this.
- Pausing stops new stake and cancellations but not queuing or claiming, by design.
