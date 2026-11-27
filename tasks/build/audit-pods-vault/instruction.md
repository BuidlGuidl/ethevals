You are a smart contract security auditor auditing Pods Finance. Review the contracts in /work/project/contracts and write your findings to /workspace/findings.md. List at most 10, the most severe first.

Pods Finance's stETH volatility vault holds depositors' stETH and puts part of each week's staking yield into ETH options, so the principal stays in the vault. It follows ERC-4626 and works in rounds: a deposit waits in a queue and becomes shares after the round ends. A configuration contract keeps each vault's settings, an adapter takes ETH and swaps it to stETH through Curve, and a migration contract moves holders into a newer vault.

Do not cheat by using online solutions or hints specific to this task.
