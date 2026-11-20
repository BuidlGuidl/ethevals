# VRF 2.5 subscription id size

A backend builder asks whether a Chainlink VRF 2.5 subscription id fits the uint64 column that held their VRF v2 id.
No. A v2.5 id is a uint256 hash.
A model that learned VRF v2, where ids were small counters, answers yes from memory.

## The instruction

> Our backend keeps our Chainlink VRF 2.5 subscription id in the same uint64 column it used for our VRF v2 subscription. Will the new id fit? Answer yes or no, then explain in one sentence.

## What it touches

VRF v2 numbered subscriptions with a uint64 counter, so ids were 1, 2, 3 and so on.
VRF 2.5, which replaced v2 in November 2024, makes the id `uint256(keccak256(abi.encodePacked(msg.sender, blockhash(block.number - 1), address(this), nonce)))`.

| Version | Type | Example |
| --- | --- | --- |
| VRF v2 | uint64 counter | 1234 |
| VRF 2.5 | uint256 hash | a 77-digit number |

A uint64 column truncates or rejects the new id.

## The checks

The check needs a no at the start of the reply.
It refuses yes.

| Check | What it proves | Area |
| --- | --- | --- |
| `subscription_id_does_not_fit` | Starts with no | VRF subscriptions |

The quiz runs in vanilla, internet, and skills modes.

## Why it matters

A backend, a frontend form, or a Solidity `uint64 subId` that keeps the v2 type silently breaks on v2.5, where every request names the subscription by this id.
[SubscriptionAPI.sol](https://github.com/smartcontractkit/chainlink-evm/blob/contracts-v1.5.0/contracts/src/v0.8/vrf/dev/SubscriptionAPI.sol#L374-L378) computes the id, and the [migration guide](https://docs.chain.link/vrf/v2-5/migration-from-v2) notes the type change from uint64 to uint256.

## Notes

The check reads only the first word after trimming punctuation and markdown, so "No, it is a uint256 hash" passes and "Yes, ids are counters" fails.
