You are a smart contract security auditor auditing CAP. Review the contracts in /work/project/contracts and write your findings to /workspace/findings.md. List at most 10, the most severe first.

CAP is a stablecoin protocol. Users deposit stablecoins into a vault to mint cUSD, and can stake cUSD in StakedCap to earn the protocol's yield. Borrowers, called agents, borrow the vault's reserves through the Lender, and restakers back each agent's loans with collateral delegated through Symbiotic. Idle reserves earn yield in outside vaults, and a fee auction sells that yield for cUSD.
