# Liquity V2 redemption fee

A stablecoin builder asks who keeps the redemption fee in Liquity V2.
The fixed answer is the redeemed Trove's borrower: the fee stays in the Trove as collateral.
Liquity V1 paid it to LQTY stakers, which makes stakers the tempting answer.

## The instruction

> In Liquity V2, when BOLD is redeemed against a Trove, who ends up with the redemption fee: the redeemer, LQTY stakers, the protocol, or the redeemed Trove's borrower? Answer with one of those four, then explain in one sentence.

## What it touches

- Redemptions. A redeemer burns BOLD and takes collateral at face value minus the fee. In V2 the fee is subtracted from the collateral lot and left in the Trove.
- What changed from V1. V1 sent redemption fees to the LQTY staking pool. V2 has no staking pool in the redemption path.

## The checks

| Check | What it proves | Area |
| --- | --- | --- |
| `redemption_fee_recipient` | The first of the four offered parties named in the reply is the borrower or the Trove, ignoring case and Markdown | Redemptions |

The check reads the first party the reply names, so an explanation that later mentions stakers or the redeemer still passes.
It checks the fixed answer, without judging the explanation.
The quiz runs in vanilla, internet, and skills modes.

## Why it matters

A frontend or script that tells borrowers a redemption costs them the fee, or tells stakers to expect it, misreports V2.
Liquity's [TroveManager](https://github.com/liquity/bold/blob/main/contracts/src/TroveManager.sol) computes `collFee` and leaves it in the Trove, with the comment "leaving the fee in the Trove", and emits `RedemptionFeePaidToTrove`.
The [README's redemption section](https://github.com/liquity/bold#redemption-fees) says the fees "are split between the borrowers hit by the redemption".
