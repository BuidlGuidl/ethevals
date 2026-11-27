# Liquity V2 zombie Trove

A stablecoin builder asks what happens to a Liquity V2 Trove that a redemption leaves with 1,500 BOLD of debt.
The fixed answer is that it becomes a zombie: it stays open, leaves the sorted list, and is unredeemable until its debt is back above the minimum.
In V1 a fully redeemed Trove was closed, which makes "closed" the tempting answer.

## The instruction

> A redemption leaves a Liquity V2 Trove with 1,500 BOLD of debt. What status does the Trove get? Answer with the status name, then explain in one sentence.

## What it touches

- Minimum debt. Liquity V2 requires 2,000 BOLD of debt per Trove, and redemptions no longer close Troves.
- Zombie Troves. A Trove redeemed below the minimum is tagged zombie and removed from the sorted list, so tiny Troves cannot clog future redemptions. Its owner brings it back above the minimum or closes it.

## The checks

| Check | What it proves | Area |
| --- | --- | --- |
| `zombie_status` | The first sentence of the reply contains the word zombie, ignoring case and Markdown | Redemptions |

It checks the fixed answer, without judging the explanation.
The quiz runs in vanilla, internet, and skills modes.

## Why it matters

A redemption script or a Trove dashboard that treats a redeemed-down Trove as closed, or as still in the redemption queue, gets V2 wrong.
Liquity's [Constants](https://github.com/liquity/bold/blob/main/contracts/src/Dependencies/Constants.sol) set `MIN_DEBT` to 2000e18, and its [TroveManager](https://github.com/liquity/bold/blob/main/contracts/src/TroveManager.sol) sets `Status.zombie` when a redemption leaves `newDebt < MIN_DEBT`.
The [README's zombie section](https://github.com/liquity/bold#zombie-troves) explains the griefing attack the status prevents.
