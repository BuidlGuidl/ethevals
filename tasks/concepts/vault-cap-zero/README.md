# Cap zero on a curated vault

Check whether a model knows that a zero vault cap still permits a supply on the vault's behalf.
The quiz checks one final reply against a fixed target.

## The instruction

```text
Our curated vault lends into several markets, each under a cap we set. We set one market's cap to zero and withdraw everything the vault had there, but leave the market on the vault's list. Can a stranger still change what our vault's shares are worth through that market? Yes or no, and if yes say how.
```

## What it touches

The target is yes, by supplying into that market on the vault's behalf.
A cap limits the vault's own allocations, but another account can name the vault as receiver.
A listed market can then change the vault's reported assets.
The rule accepts a leading yes plus on-behalf, for-the-vault, receiver, or donation wording.

## The checks

| Check | What it proves | Area |
| --- | --- | --- |
| `supply_on_behalf` | The reply starts with yes and names a supply on behalf or donation | vault caps |

The quiz runs in vanilla, internet, and skills modes.

## Why it matters

A zero cap alone does not remove a market from the vault's asset accounting.
The [Resolv incident account](https://rekt.news/resolv-labs-rekt) describes attackers supplying on behalf of vaults after curators set caps to zero.
