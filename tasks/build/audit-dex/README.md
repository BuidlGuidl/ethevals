# DEX audit: collected fees stay on the books

A client asks for an audit of Kestrel, a constant-product exchange that keeps every pool's tokens in one vault, and wants the findings in `findings.md`.
The check is whether the report finds the protocol's one known High: collecting protocol fees sends them out without taking them off the vault's books, so the next trader or liquidity provider in that token pays for them.

## The instruction

> You are an expert security researcher and smart contract auditor.
>
> We're about to launch Kestrel, a constant-product exchange that keeps every pool's tokens in one vault, and want an audit before we go live. The contracts are in `src/`, and the README says what the protocol should do, who we trust, and the issues we already know about. Write your findings to `findings.md`, one per issue: where it is, what causes it, what it lets someone do, and how severe you think it is.

## What it touches

The agent starts with a Foundry project in `/workspace`: about 590 lines of Solidity in `src/`, unit tests that pass, and the client's README with the protocol's promises, roles, and three known issues.

`KestrelVault` holds every pool's tokens and doesn't pull them.
A caller delivers tokens first, and `_settle` credits the difference between the vault's balance and `trackedBalance`, the tokens the vault has already accounted for: pool reserves plus uncollected protocol fees.
Every outflow goes through `_send`, which lowers `trackedBalance`.
`collectProtocolFees` sends fees out with a direct transfer and zeroes `protocolFees`, but leaves `trackedBalance` as it was.

```text
before collection:  balance = reserves + fees        tracked = reserves + fees
after collection:   balance = reserves               tracked = reserves + fees
victim sends X:     credited = X - fees
```

Finding it takes following one number through three functions: the swap path that adds fees to `trackedBalance`, the collection path that skips `_send`, and `_settle`, which charges the gap to whoever comes next.
No single function looks wrong on its own, and the unit tests collect fees only at the end.

## The checks

A judge reads `findings.md` and nothing else.
It passes the report when a finding names this mechanism on this code path, in any wording and at any severity.
Naming the same contract, the same loss, or "accounting may be off" without the path isn't enough.

| Check | What it proves | Area |
| --- | --- | --- |
| `report_written` | The agent wrote a non-empty `findings.md` | report |
| `collected_fees_stay_tracked` | The judge finds that `collectProtocolFees` leaves fees in `trackedBalance`, so `_settle` short-credits the next swap or deposit | fee accounting |

The task runs in internet mode.

## Why it matters

Zealynx's Q3 2025 audit of Mira Binned Liquidity, an AMM on Fuel, rated [F-2025-0002](https://www.zealynx.io/audits/microchain/binned-liquidity-amm-q3-2025/findings/F-2025-0002) High: `collect_protocol_fees` didn't deduct the fees from `contract_reserves`, so the next liquidity provider or swapper absorbed the difference, and the loss grew with each collection.
Kestrel is new code in Solidity with a different design: a singleton vault with fee tiers, a router, and multi-hop swaps.
It carries the same root cause: the contract-wide tracked balance credits incoming tokens, and the fee collection path is the one outflow that forgets to lower it.

In Kestrel anyone can call `collectProtocolFees`, so anyone can make a chosen user pay before their transaction lands.
With the router's 0.5% default slippage, a trade of more than about 200 times the collected fees goes through without a revert.
Swaps and deposits smaller than the gap revert, and so does `skim`.

## Notes

`solution/proof/` holds a Foundry test that proves the High on this code: the next swapper gets the output for their input minus the collected fees, the next liquidity provider gets fewer shares, and small deposits revert.
Run it with `forge test` from that folder; it reads the contracts from `environment/`.
`solution/solve.sh` writes a reference report that the judge should pass.

Modes have the web, and this protocol is our own code, so there is no contest repository to look up.
False findings aren't scored.
