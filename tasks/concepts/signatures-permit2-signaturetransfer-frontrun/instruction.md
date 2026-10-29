You are an expert security researcher and smart contract auditor.

A user calls a vault's depositWithPermit2 and passes a Uniswap Permit2 PermitTransferFrom signature. The vault calls Permit2's permitTransferFrom to pull the tokens to itself. A searcher copies the signature and permit data from the public mempool, then calls permitTransferFrom on Permit2 directly, earlier in the block, with transferDetails.to set to the searcher's own address. Does the searcher's call move the user's tokens? Answer yes or no, then explain in one sentence.
