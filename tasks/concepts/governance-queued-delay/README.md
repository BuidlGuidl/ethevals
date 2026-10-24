# Queued delay

Check whether a model preserves the wait for proposals that a timelock has already queued.
The quiz checks one final reply against a fixed target.

## The instruction

```text
We're designing the timelock that will hold our DAO's treasury. If a passed proposal lowers the delay, should proposals that are already queued and waiting get the shorter delay? Answer yes or no, and say in a few words why.
```

## What it touches

The target is no, because each operation keeps the wait set when the timelock queued it.
Reading the current delay at execution lets one delay reduction shorten the wait for every operation behind it.
The rule accepts an opening no and wording about a fixed queue time or bypassing the wait.
It ignores case and markdown marks, and accepts the prefix "Short answer:" before no.

## The checks

| Check | What it proves | Area |
| --- | --- | --- |
| `queued_delay_fixed` | The reply opens with no and describes a fixed wait or the risk of bypassing it | timelocks |

The quiz runs in vanilla, internet, and skills modes.

## Why it matters

A timelock gives holders time to react before a passed proposal changes contracts or moves treasury funds.
OpenZeppelin's [TimelockController](https://github.com/OpenZeppelin/openzeppelin-contracts/blob/v5.7.0/contracts/governance/TimelockController.sol) stores each operation's ready time when scheduling it.
The [Zodiac Delay contract](https://github.com/zodiaceco/zodiac-modifier-delay/blob/main/contracts/Delay.sol) instead reads the current cooldown at execution.
The [Nexus Mutual incident report](https://nexusmutual.io/blog/term-finance-governance-takeover-incident-report) describes Term Finance's attacker setting that cooldown to zero before draining assets.
