# Shut off a phishing site's signatures

A wallet user signed several requests on a fake airdrop site and asks the agent to make sure the site can't take anything with them, without breaking the approvals they use every day.
The task checks that every signature the site collected is dead, not just that the approvals on the chain are gone, by replaying each one as the thief.

## The instruction

> i signed some stuff on a fake site about an hour ago, i thought it was the uniswap airdrop claim. i don't think anything is gone yet. site-requests.json is everything the site asked my wallet for, exported from the wallet. make sure whoever runs that site can't take anything with what i gave them. i use this wallet every day for uniswap and opensea, so don't break the rest. my wallet, its key and my tokens are in chain_context.json. do it on that chain and tell me what you did.

## What it touches

- **An onchain grant.** One request was a transaction: `setApprovalForAll` on the user's NFT collection, naming the thief as operator. It is the only grant an approval checker shows.

- **Two EIP-2612 permits.** The site collected a signed USDC `Permit` for an unlimited amount, valid for 30 days, then asked for it again. The second one is signed at nonce 1, not nonce 0. Neither is on the chain until someone submits it. `approve(thief, 0)` does not touch them: the thief submits one afterwards and gets the allowance back. Using up nonce 0 kills the first and makes the second valid, because nonce 1 is now next. Only using up both nonces kills both.

- **A Permit2 allowance signature.** The site collected a `PermitBatch` for USDC and WETH. Permit2's `lockdown` and `approve(token, spender, 0, 0)` zero the amount and leave the nonce, so the signature still works afterwards. Only `invalidateNonces` for each token, or submitting the signature first and then zeroing the allowance, kills it.

- **A Permit2 transfer signature.** The site collected a `PermitTransferFrom` for the wallet's WETH. It uses Permit2's unordered nonces, which `invalidateNonces` does not touch. It dies only through `invalidateUnorderedNonces`, with the nonce's word and bit.

- **The rest of the wallet.** The wallet approves Permit2 for USDC and WETH, holds Permit2 allowances for Uniswap's Universal Router, and lets OpenSea's conduit move its NFTs. Revoking the tokens' approvals to Permit2 does block both Permit2 signatures, but it breaks the user's Uniswap. The signed USDC permits don't go through Permit2, so revoking still leaves them live.

- **Noise.** A `personal_sign` login message grants nothing. A transaction the user rejected sent nothing.

## The checks

Setup puts Permit2's mainnet bytecode at its usual address on a fresh chain. It deploys a USDC with EIP-2612 permits, WETH, and an NFT collection, and gives a random wallet 18,420 USDC, 6.2 WETH and two NFTs.
It replays a month of everyday approvals, then the phishing visit an hour ago, and writes the wallet's request log to `site-requests.json`.
The thief's address and every signature are random for each trial.
Only `chain_context.json` and `site-requests.json` appear in the agent's folder.

The [Python checks](tests/phishing_checks.py) first read the wallet as the agent left it.
Then they act as the thief, who has gas and keeps every signature.
They first try each approval and allowance, then replay each signature, and after each move they try to take one unit of the token, or one NFT.

| Check | What it proves | Area |
| --- | --- | --- |
| `signatures_cannot_be_replayed` | "Can't take anything with what i gave them": replayed by the thief in nonce order, none of the two USDC permits, the Permit2 batch, or the Permit2 transfer signature moves any token. Source: the thief's balances around each replay. | Signatures |
| `no_grants_left_for_the_thief` | Before any replay, the thief can take nothing through the NFT operator approval, a token allowance, or a Permit2 allowance. Source: the thief's balances around each attempt. | Approvals |
| `everyday_approvals_intact` | "Don't break the rest": USDC and WETH still approve Permit2 for the maximum, the Permit2 allowances to Uniswap's Universal Router keep their amount and have not expired, and OpenSea's conduit is still an operator for the NFTs. Source: allowance reads when the agent stopped. | Scope |
| `holdings_stay_in_wallet` | The wallet still holds all its USDC, WETH, and both NFTs when the agent stops. Source: balance reads when the agent stopped. | Scope |

## Why it matters

Revoke.cash, the most used approval checker, [says it can never tell which signatures a wallet has signed](https://revoke.cash/learn/approvals/what-are-eip2612-permit-signatures): a permit's approval shows up on its dashboard only once the scammer has submitted it.
So a user who cleans up what the dashboard shows still leaves every unused signature live.
In Permit2's source, [`lockdown`](https://github.com/Uniswap/permit2/blob/main/src/AllowanceTransfer.sol) sets amounts to zero and leaves nonces alone. `invalidateNonces` sits next to it, and [`invalidateUnorderedNonces`](https://github.com/Uniswap/permit2/blob/main/src/SignatureTransfer.sol) is a separate call for transfer signatures.
[Scam Sniffer's 2024 report](https://drops.scamsniffer.io/scam-sniffer-2024-web3-phishing-attacks-wallet-drainers-drain-494-million/) counts $494 million drained by phishing, and says permit remains the main method for token phishing: 56.7% of the large losses came from permit signatures.

## Notes

- Permit2's mainnet code caches chain ID 1 and recomputes its domain separator on any other chain, so signatures for this chain's ID verify as they would on a fork.
- The Universal Router and OpenSea conduit addresses carry stub code that reverts any call. The task only reads the wallet's approvals to them.
- The solution reads `site-requests.json`. It revokes the operator approval, uses up USDC permit nonces 0 and 1 with zero-value permits it signs itself, calls `invalidateNonces` for both tokens of the batch, and calls `invalidateUnorderedNonces` for the transfer signature.
- Submitting each phishing signature itself and then zeroing what it granted also passes.
- Scripted strategies on a local chain: doing nothing fails both thief checks. Revoking what an approval checker shows (operator, allowances, `lockdown`) fails `signatures_cannot_be_replayed` on all four signatures. Invalidating only the ordered Permit2 nonces leaves both USDC permits and the transfer signature live. Revoking the tokens' approvals to Permit2 fails `everyday_approvals_intact` and still leaves the USDC permits live. Doing everything right but using up only nonce 0 leaves the second USDC permit live.
- The first version had one USDC permit. Claude Code on Opus 5.5 and Codex on GPT-6.2 Sol both passed it with the solution's approach.
