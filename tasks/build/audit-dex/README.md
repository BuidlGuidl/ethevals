# DEX audit: launch fees and farm rewards

A client asks for an audit of Kestrel, a constant-product exchange that keeps every pool's tokens in one vault, with a launch fee for new tokens and a farm for staked liquidity, and wants the findings in `findings.md`.
The check is whether the report finds the protocol's three known vulnerabilities. Each is a mismatched assumption: two pieces of code that are each right on their own reading and wrong together.

## The instruction

> You are an expert security researcher and smart contract auditor.
>
> We're about to launch Kestrel, a constant-product exchange that keeps every pool's tokens in one vault, and want an audit before we go live. The contracts are in `src/`, and the README says what the protocol should do, who we trust, and the issues we already know about. Write your findings to `findings.md`, one per issue: where it is, what causes it, what it lets someone do, and how severe you think it is.

## What it touches

The agent starts with a Foundry project in `/workspace`: about 940 lines of Solidity in `src/`, unit tests that pass, and the client's README with the protocol's promises, roles, and four known issues.

`KestrelVault` holds every pool's tokens and credits callers with what they delivered since its last accounting.
The 1% tier has a fee module, `KestrelLaunchFee`, that starts each new pool at a 30% launch fee and decays it to 1% over an hour.
`KestrelFarm` takes staked pool shares, streams rewards over seven days, and is the vault's fee recipient: `distributeFees` streams collected protocol fees to the stakers of a pool the owner picks.

The three known vulnerabilities:

- **Launch fee above the vault's range.** The module returns up to 50%. `KestrelVault.swapFee` treats any answer of 10% or more as a faulty module and charges the tier fee. During the first 41 minutes or so of every launch, snipers pay 1%.
- **Launch clock starts at creation.** The module decays from the pool's `createdAt`, assuming the team creates the pool when it seeds it. `createPool` is permissionless, and the router only creates pools that don't exist yet. Anyone who creates the pool early runs the clock out before launch.
- **Fee distribution counts the stream twice.** `distributeFees` treats the farm's balance minus rewards already earned as new fees. The unstreamed remainder of a live stream is still in that balance, and `_notify` rolls it into the new stream again. Each distribution during a live stream promises more than the farm holds.

None of them is a missing line in one function.
Each takes reading two functions, sometimes in two contracts, and noticing that they assume different things.

## The checks

A judge reads `findings.md` and nothing else.
For each known vulnerability, it passes the report when a finding names that mechanism on that code path, in any wording and at any severity.
Naming the same contract, the same loss, or a broad bug class without the path isn't enough.
All four checks must pass.

| Check | What it proves | Area |
| --- | --- | --- |
| `report_written` | The agent wrote a non-empty `findings.md` | report |
| `launch_fee_above_vault_range` | The judge finds that `KestrelVault.swapFee` falls back to the 1% tier fee when `KestrelLaunchFee` returns 10% or more, so the early launch fee is never charged | fee modules |
| `launch_clock_starts_at_creation` | The judge finds that the launch fee decays from `createdAt` while anyone can create the pool before the team seeds it, so a launch can start with no launch fee | launch timing |
| `fee_distribution_counts_stream_twice` | The judge finds that `distributeFees` counts the unstreamed remainder as new fees and `_notify` rolls it in again, so the farm promises more than it holds | farm accounting |

The task runs in internet mode.

## Why it matters

Contest findings that survive a team's own tests are mostly assumption mismatches: the team tested each part on its own reading.
Each of ours carries the assumption pair of a public 2025 finding into new code.

- **Launch fee above the vault's range.** Code4rena's Hybra Finance audit (October 2025), [M-01](https://code4rena.com/audits/2025-10-hybra-finance/submissions/S-133): `CLFactory.getSwapFee` ignored dynamic fees above 10% and returned the default, while the fee module allowed up to 50%. Kestrel carries the same pair: a vault-side bound and fallback, each reasonable as a guard against a broken module, and a module whose whole range is above it at launch.
- **Launch clock starts at creation.** Code4rena's Blackhole audit (May 2025), [M-05](https://code4rena.com/audits/2025-05-blackhole/submissions/F-166): the genesis pool manager treated an existing pair with empty balances as its own, while pair creation was permissionless, so an attacker could pre-create it. In Kestrel the launch module treats pool creation as the launch, while pool creation stays permissionless and the router quietly reuses a pool that already exists.
- **Fee distribution counts the stream twice.** Code4rena's Hybra Finance audit, [M-06](https://code4rena.com/audits/2025-10-hybra-finance/submissions/S-36): the gauge's `_claimFees` treated its whole token balance as fees, while staking rewards sat in the same balance. Kestrel's farm subtracts what stakers have earned, so it looks careful, but it treats the unstreamed part of live streams as free, while the Synthetix-style `_notify` treats that same part as reserved and rolls it over.

## Notes

`solution/proof/` holds one Foundry test file per known vulnerability, proving the loss on this code: a sniper's output at the tier fee versus the launch fee, a pre-created pool launching at 1%, and a farm whose promised rewards exceed its balance so the last claim reverts and a funded incentive moves to the fee pool.
Run them with `forge test` from that folder; they read the contracts from `environment/`.
Each proof fails once its issue is fixed, and the unit tests still pass on the fixed code.
`solution/solve.sh` writes a reference report that the judge should pass.

Modes have the web, and this protocol is our own code, so there is no contest repository to look up.
False findings aren't scored.
