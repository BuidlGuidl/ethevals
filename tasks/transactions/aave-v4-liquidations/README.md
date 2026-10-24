# Liquidate Aave V4 borrowers

A liquidation keeper must add Aave V4's Main Spoke and act on its watchlist.
The task checks repayment limits, small debt, collateral choice, profit, and the keeper's report on a mainnet fork.

## The instruction

```text
our liquidation bot runs against aave v3 on mainnet and still ignores v4, live since march. add v4's main spoke on the core hub. chain_context.json has the chain, our wallet (it holds USDC for repayments and ETH for gas) and the borrowers we watch. for each one that's liquidatable, repay as much as the protocol lets us and take the collateral. run it on that chain now, and write what you did to liquidations.json: one entry per liquidation with borrower, debt repaid in USDC, collateral seized.
```

## What it touches

V4 liquidations take reserve ids and stop at the Spoke's target health factor.
The liquidator must approve the Spoke to spend USDC.
The Hub holds liquidity but does not pull the liquidator's tokens.

A repayment that leaves less than $1,000 of debt can revert with `MustNotLeaveDust`.
Passing the maximum uint lets the protocol choose the amount and clear small debt in full.
A borrower with two collaterals can need more than one call.
Supplied shares remain on the Spoke when the liquidator chooses `receiveShares`.

## The checks

| Check | What it proves | Area |
| --- | --- | --- |
| `compile` | The tests compile next to the agent's files. | all |
| `test_underwaterPositionsBroughtToTarget` | Every underwater borrower reaches the Spoke's target health factor or has no debt. | repayment limits |
| `test_smallPositionClearedWhole` | The small borrower's USDC debt clears in full. | dust |
| `test_healthyPositionUntouched` | The healthy borrower's debt shares and collateral shares stay unchanged, apart from asset interest. | borrower selection |
| `test_keeperCameOutAhead` | The wallet retains at least one quarter of the liquidation bonus on the debt it repaid. | profit |
| `test_reportMatchesChain` | Each report entry matches one liquidation event within 1%, without missing or duplicate entries. | reporting |

The report check matches entries without regard to order by borrower, collateral, repayment, and seized amount.
Two liquidations of borrower D need two entries, including when both calls seize the same token.
The solution writes an array with `borrower`, `debtRepaidUSDC`, and `collateralSeized` fields.
The last field contains a token address and an amount.
Amounts can use decimal token units or integer base units; the parser accepts common camel-case and snake-case field names.
The check counts collateral paid to the liquidator after the protocol fee, including supplied shares valued as underlying assets.

## Why it matters

[Aave launched V4 on Ethereum on March 30, 2026](https://aave.com/blog/aave-v4-live-ethereum).
The [liquidation engine overview](https://governance.aave.com/t/overview-of-aave-v4-s-liquidation-engine/23531) explains target health factors and the variable bonus.
[Aave's engine article](https://aave.com/blog/aave-v4-liquidations) also explains the debt dust rule.
Keepers that reuse V3's close factor can leave liquidatable positions behind.

The [supply](https://aave.com/docs/aave-v4/positions/supply.md), [repay](https://aave.com/docs/aave-v4/positions/repay.md), and [liquidation](https://aave.com/docs/aave-v4/positions/liquidations.md) snippets disagree with the deployed interface.
At authoring, they approved the Hub, and the liquidation snippet omitted the fifth argument.
The [Spoke interface](https://github.com/aave/aave-v4/blob/v0.5.11/src/spoke/interfaces/ISpoke.sol) and chain calls define the calls used here.

## Notes

Setup pins Ethereum block 26,256,000 and creates four fresh borrowers through unlocked accounts.
It supplies WETH for A, B, and C, and both WETH and WBTC for D.
A, C, and D borrow 20,000 USDC; B borrows 1,500 USDC.
Setup replaces the WETH oracle source's code with a fixed price 25% below its starting value.
A and B end near health factor 0.97, C above 1.4, and D near 0.92.
Neither collateral alone can bring D to the target.
The solution takes WETH first so D remains liquidatable for the WBTC call.

The fresh keeper holds 150,000 USDC and 10 ETH.
Its context lists the chain, wallet, Hub, Spoke, and watchlist, without reserve ids or health factors.
The private context records debt, collateral, health factors, prices, wallet balances, and the target health factor.
The tests read the live chain and collect Spoke liquidation events after setup.
The report lives at `/workspace/liquidations.json`, beside `chain_context.json`, as in the vault task's workdir.
The verifier parses it before Forge starts and copies its data into a private temporary context.
Reward Kit requires every check to pass.
