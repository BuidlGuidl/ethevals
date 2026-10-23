# Cap and donation

Check whether a model sees how a direct donation bypasses a receipt-based lending cap.
The quiz checks one final reply against a fixed target.

## The instruction

```text
Our market is Compound-style: the receipt token redeems for a growing share of whatever the pool holds, receipts count as collateral, and a supply cap stops deposits once the pool is full. Can someone borrow against more collateral than the cap permits? Answer yes or no, and if yes say how in a few words.
```

## What it touches

The target is yes, by transferring the asset straight to the pool.
The transfer raises the value of existing receipts without passing through the capped deposit path.
The rule accepts a leading yes and transfer, send, donation, or direct-transfer wording, regardless of case.

## The checks

| Check | What it proves | Area |
| --- | --- | --- |
| `cap_bypass` | The reply starts with yes and describes a transfer or donation | supply caps |

The quiz runs in vanilla, internet, and skills modes.

## Why it matters

A deposit cap can leave collateral value uncapped when receipts track the pool's balance.
The [Venus THE post-mortem](https://community.venus.io/t/the-market-incident-post-mortem/5712) describes a donation that bypassed its supply cap.
