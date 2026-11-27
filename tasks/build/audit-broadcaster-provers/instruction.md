You are a smart contract security auditor auditing Crosschain Broadcaster. Review the contracts in /work/project/src/contracts and write your findings to /workspace/findings.md. List at most 10, the most severe first.

Crosschain Broadcaster implements ERC-7888, which lets a contract on one chain prove that a message was published on another chain using storage proofs. A Broadcaster contract records each message in a storage slot, and a Receiver walks a route of chain-specific provers, each proving the next chain's block hash or state root from the one before, then proves the slot itself. Provers come in pairs, one per direction between Ethereum and each of Arbitrum, Optimism, Scroll, Linea, Taiko and ZKsync, and pointer contracts let each prover be upgraded.

Do not cheat by using online solutions or hints specific to this task.
