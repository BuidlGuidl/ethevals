# Wrapped quorum

Check whether a model distinguishes the vote token's supply from the underlying token's supply.
The quiz checks one final reply against a fixed target.

## The instruction

```text
Our DAO's token is a plain ERC-20, so holders wrap it one to one into a vote token when they want to vote. The governor sets quorum as 4% of the vote token's total supply. Does that give us a 4% quorum of our token? Answer yes or no, and if no say in a few words what quorum is really measured against.
```

## What it touches

The target is no, because quorum measures only the tokens that holders have wrapped.
Wrapping is opt-in, so 4% of the vote token's supply can be a tiny share of the underlying token's supply.
The rule accepts an opening no and wording about wrapped tokens, deposits, opted-in holders, or vote token supply.
It ignores case and markdown marks, and accepts the prefix "Short answer:" before no.

## The checks

| Check | What it proves | Area |
| --- | --- | --- |
| `wrapped_supply_quorum` | The reply opens with no and identifies the wrapped supply as the quorum basis | quorum |

The quiz runs in vanilla, internet, and skills modes.

## Why it matters

Low wrapping participation can leave a treasury under the control of a small share of token holders.
OpenZeppelin's [governance guide](https://docs.openzeppelin.com/contracts/5.x/governance) describes wrapping an existing ERC-20 into a vote token.
Its [quorum module](https://github.com/OpenZeppelin/openzeppelin-contracts/blob/v5.7.0/contracts/governance/extensions/GovernorVotesQuorumFraction.sol) reads that vote token's past total supply.
The [Nexus Mutual incident report](https://nexusmutual.io/blog/term-finance-governance-takeover-incident-report) attributes Term Finance's small electorate to opt-in wrapping.
It reports that a single share cleared quorum because participation used wrapped supply rather than LP supply.
