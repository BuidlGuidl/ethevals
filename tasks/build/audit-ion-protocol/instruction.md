You are a smart contract security auditor auditing Ion Protocol. Review the contracts in /work/project/src and write your findings to /workspace/findings.md. List at most 10, the most severe first.

Ion Protocol is a lending market where users borrow WETH against liquid staking tokens such as wstETH, ETHx and swETH. IonPool keeps the loans and the lenders' deposits, GemJoin contracts hold the collateral, and the Liquidation contract closes unhealthy vaults. Each collateral has its own price oracles, and helper contracts open, repay and lever up positions in one transaction.

Do not cheat by using online solutions or hints specific to this task.
