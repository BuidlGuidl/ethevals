You are an expert security researcher and smart contract auditor.

Does the shared `@nonreentrant("lock")` annotation prevent a callback from `withdraw` from entering `deposit` in a pool compiled with Vyper 0.2.16? Both functions use that annotation, but `withdraw` sends ETH before updating the balance that `deposit` reads. You are auditing the deployed bytecode's protection, not proposing a source rewrite. Answer yes or no, then explain in one sentence.
