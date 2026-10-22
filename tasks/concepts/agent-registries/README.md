# Agent registries

A one-line knowledge question about the standard that lets AI agents find and trust each other on Ethereum.
The answer is [ERC-8004](https://eips.ethereum.org/EIPS/eip-8004), Trustless Agents.

## The instruction

```text
which ERC defines onchain identity, reputation and validation registries for AI agents? just the number please
```

## What it touches

- **Standards for agents.** ERC-8004 gives agents three onchain registries. The Identity Registry gives each agent an ERC-721 handle that points to its registration file. The Reputation Registry holds feedback from the agent's clients. The Validation Registry records checks by independent validators, such as stakers who re-run a job.

## The checks

| Check | What it proves | Area |
| --- | --- | --- |
| `erc_number` | The reply ends with 8004, once spaces and punctuation are trimmed from both ends | standards for agents |

The quiz runs in all three modes.
In the vanilla mode, a bare model answers in one API call from what it learned in training.
In the internet and skills modes, an agent can look the answer up.

## Why it matters

Agents that hire, pay, or check each other need a shared way to find one another and decide whom to trust.
ERC-8004 is that shared way, so a model that knows it builds on the standard instead of inventing its own registry.
The ERC was created in August 2025, so a model trained before then can't know it.
