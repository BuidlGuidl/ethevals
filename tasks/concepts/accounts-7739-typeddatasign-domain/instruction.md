You are an expert security researcher and smart contract auditor.

You are reviewing a smart account's ERC-7739 isValidSignature. A dapp asks the account's owner to sign an EIP-712 Order under the dapp's own domain, and the account verifies it through the TypedDataSign workflow. In the final digest the owner's key signs, which domain separator comes right after the 0x1901 prefix: the dapp's or the account's? Answer dapp or account, then explain in one sentence.
