You are a smart contract security auditor auditing Tribunal. Review the contracts in /work/project/src and write your findings to /workspace/findings.md. List at most 10, the most severe first.

Tribunal settles cross-chain swaps on chains that order transactions by priority fee. A sponsor locks tokens in The Compact and signs a mandate listing the fills that may settle it, an adjuster co-signs which fill is live, and a filler executes that fill while Tribunal, acting as the arbiter, claims the locked tokens. Bridges and messaging layers inherit Tribunal to carry the result between chains, and ERC7683Tribunal adapts it to ERC-7683.

Do not cheat by using online solutions or hints specific to this task.
