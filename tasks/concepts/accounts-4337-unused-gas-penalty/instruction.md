You are an expert security researcher and smart contract auditor.

You are reviewing a verifying paymaster for EntryPoint v0.7. It signs any user operation from the app's users with callGasLimit up to 5,000,000 and pays from its EntryPoint deposit. A bundler can register as an app user, submits its own operations with callGasLimit set to 5,000,000 each time, and keeps the fees. Is the paymaster charged only for the gas each operation actually used? Answer yes or no, then explain in one sentence.
