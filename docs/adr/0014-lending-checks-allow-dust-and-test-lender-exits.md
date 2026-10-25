---
status: accepted
---

# Lending checks allow cash dust and test lender exits

The token lending market checks rejected one unit of cash dust and required a particular debt write-off mechanism.
Both checks must accept sound accounting designs while rejecting claims that the market cannot pay.

## Decision

Booked supply minus booked borrowing cannot exceed cash.
Cash can exceed that net amount by at most five USDC base units.

After collateral runs out, liquidation must charge only the covered debt and transfer all collateral to the liquidator.
Both equal lenders must receive their full reported claims in either withdrawal order.
Their claims must share the loss within five USDC base units.
The books must balance before and after those withdrawals.
The check does not require the market to erase the borrower's remaining debt.

Check names and the all-pass reward rule stay the same.
The instruction, interfaces, and solution stay the same.

## Evidence

Compare local Forge results for Kimi K3, Opus 5.5, GPT-6.1-sol, and the solution before and after the change.
A phantom-debt mutant must fail when its lender claims exceed the cash available for both withdrawals.
A mutant that books one unit more than cash must fail the books check.
