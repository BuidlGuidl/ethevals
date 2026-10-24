# Signed votes

A team stores signed votes in its backend.
Its holders include EOAs, a 2-of-3 Safe, and smart wallets.
The checks call the agent's TypeScript module with signatures from real wallets on a mainnet fork.

## The instruction

```text
holders vote on proposals by signing, and our backend stores each vote if it's valid. big holders vote
from a 2-of-3 Safe, so a vote can take them a day or two to finish. many newer holders use smart wallets.
in src/votes.ts, export voteToSign({ proposalId, voter, support }), returning the typed data the voter
signs, and checkVote({ proposalId, voter, support }, signature), resolving to true if we should store the vote. we're on
mainnet; the RPC URL is in RPC_URL.

proposalId is a bigint, voter is an address, and support is 0, 1, or 2 (against, for, abstain).
voteToSign can be async. Its result is the object that viem's signTypedData takes.
checkVote receives those vote fields and a hex signature, and resolves to a boolean.
```

## What it touches

- A Safe decides whether a signature meets its threshold onchain. Recovering one owner does not prove the Safe signed.
- Smart wallets can sign before deployment. Their ERC-6492 signature carries the factory call needed to check the signature.
  Smart wallets built on viem's account tooling (ZeroDev, Biconomy, Alchemy, MetaMask's kit), plus Ambire, thirdweb, Sequence, and Openfort, [wrap undeployed account signatures in ERC-6492](https://github.com/wevm/viem/blob/viem@2.57.11/src/account-abstraction/accounts/toSmartAccount.ts#L113-L137).
- A vote must bind its proposal and support. Changing either must invalidate the signature.
- The backend rebuilds the typed data from the vote fields. A client-supplied domain cannot define what the backend accepts.
- Collecting two Safe owners can take a day or two. Signed votes must remain valid after that delay.

## The checks

The fork starts at mainnet block 23,819,000.
The environment has viem 2.57.11, TypeScript, tsx, and Foundry, with dependencies installed before the agent starts.
Setup funds the account in `chain_context.json` with 10 ETH.
The verifier makes its own local fork of the sidecar after the agent stops.
It deploys the wallet fixtures through their real factories.
It uses chain controls only on that private fork to fund fixture accounts and advance time.
The agent's `RPC_URL` points at the sidecar during work and at the verifier fork during checks.

| Check | What it proves | Instruction sentence | Area |
| --- | --- | --- | --- |
| `compile` | The module loads through tsx and exports both functions | "in src/votes.ts, export voteToSign ... and checkVote" | interface |
| `eoa_vote` | An EOA's own vote is accepted | "our backend stores each vote if it's valid" | EOA |
| `tampered_vote` | A signature cannot authorize another support value | "our backend stores each vote if it's valid" | binding |
| `wrong_signer` | Another EOA cannot sign for the voter | "our backend stores each vote if it's valid" | binding |
| `other_proposal` | A signature cannot authorize another proposal | "holders vote on proposals by signing" | binding |
| `safe_vote` | Two sorted Safe owner signatures are accepted | "big holders vote from a 2-of-3 Safe" | Safe |
| `safe_one_owner` | One Safe owner cannot meet the threshold | "big holders vote from a 2-of-3 Safe" | Safe |
| `safe_late_vote` | A Safe vote remains valid after 40 hours | "so a vote can take them a day or two to finish" | delay |
| `safe_onchain_approval` | A threshold-approved SafeMessage accepts an empty signature | "big holders vote from a 2-of-3 Safe" | Safe |
| `safe_onchain_unapproved` | An unapproved SafeMessage rejects an empty signature | "our backend stores each vote if it's valid" | Safe |
| `smart_wallet_new` | An undeployed Coinbase wallet's ERC-6492 signature is accepted | "many newer holders use smart wallets" | smart wallets |
| `smart_wallet_deployed` | A deployed Coinbase wallet's signature is accepted | "many newer holders use smart wallets" | smart wallets |

Each negative check also requires its matching positive check to pass.
The checks sign typed data from `voteToSign` and pass plain vote fields to `checkVote`.
A thrown error from `checkVote` counts as rejection on negative checks and fails positive checks.
The delayed Safe check asserts that the verifier fork advances by at least 40 hours before the owners finish signing.
The checks do not require domain names, struct names, storage, or a nonce scheme.
RewardKit reads the named records in `checks.json` and awards 1 only when every check passes.

## Why it matters

Viem's [standalone verification utility](https://github.com/wevm/viem/blob/viem%402.57.11/src/utils/signature/verifyMessage.ts#L39-L55) recovers an EOA.
Its [public client action](https://github.com/wevm/viem/blob/viem%402.57.11/src/actions/public/verifyHash.ts#L155-L197) also asks the chain.
The [siwe contract check](https://github.com/spruceid/siwe/blob/911f6f2/packages/siwe/lib/utils.ts#L22-L35) calls ERC-1271 directly, which cannot deploy an undeployed signer.
[Snapshot's verification order](https://github.com/snapshot-labs/snapshot.js/blob/v0.17.6/src/verify/evm.ts#L31-L111) reflects these distinct signing paths.

Safe [hashes the app digest inside SafeMessage](https://github.com/safe-global/safe-smart-account/blob/v1.4.1/contracts/handler/CompatibilityFallbackHandler.sol#L56-L80).
Safe{Wallet} [hands over the signature at threshold](https://github.com/safe-global/safe-wallet-monorepo/blob/d758ef1/apps/web/src/services/safe-messages/safeMsgNotifications.ts#L4-L6).
Snapshot [routes `0x` signatures to its relayer](https://github.com/snapshot-labs/snapshot.js/blob/v0.17.6/src/sign/index.ts#L95-L96).
Its relayer [polls the Safe's onchain message approval](https://github.com/snapshot-labs/snapshot-relayer/blob/ed7f18a/src/check.ts#L95-L130).
Viem [wraps undeployed smart account signatures in ERC-6492](https://github.com/wevm/viem/blob/viem@2.57.11/src/account-abstraction/accounts/toSmartAccount.ts#L113-L137).
A backend that treats every signer as an EOA rejects these holders even when their wallets sign correctly.

## Notes

This task needs `MAINNET_RPC_URL` for state at block 23,819,000.
Without it, the free check skips oracle and nop trials.
Viem 2.57.11's [ERC-6492 verifier](https://github.com/wevm/viem/blob/viem%402.57.11/contracts/src/ERC6492SignatureVerifier.sol#L71-L77) requires at least 32 signature bytes before checking ERC-1271.
Its public client action rejects `0x` even when the Safe approves that message onchain.
The solution calls ERC-1271 directly for `0x` and uses the public client action for other signatures.
The checks do not enforce a particular domain or message layout.
