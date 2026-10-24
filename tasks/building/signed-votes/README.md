# Signed votes

A team stores signed votes in its backend.
Its holders include EOAs, a 2-of-3 Safe, and smart wallets.
The checks call the agent's TypeScript module with signatures from real wallets on a mainnet fork.

## The instruction

```text
holders vote on proposals by signing, and our backend stores each vote if it's valid. big holders vote
from a 2-of-3 Safe, so a vote can take them a day to finish. many newer holders use smart wallets.
in src/votes.ts, export voteToSign({ proposalId, voter, support }), returning the typed data the voter
signs, and checkVote(typedData, signature), resolving to true if we should store the vote. we're on
mainnet; the RPC URL is in RPC_URL.

proposalId is a bigint, voter is an address, and support is 0, 1, or 2 (against, for, abstain).
voteToSign can be async. Its result is the object that viem's signTypedData takes.
checkVote receives that same object and a hex signature, and resolves to a boolean.
```

## What it touches

- A Safe decides whether a signature meets its threshold onchain. Recovering one owner does not prove the Safe signed.
- Smart wallets can sign before deployment. Their ERC-6492 signature carries the factory call needed to check the signature.
- A vote must bind its proposal and support. Changing either must invalidate the signature.
- Collecting two Safe owners can take a day. Signed votes must remain valid after that delay.
- An EOA can delegate its execution to a contract through EIP-7702 and still sign with its own key.

## The checks

The fork starts at mainnet block 23,819,000.
The environment has viem 2.57.11, TypeScript, tsx, and Foundry, with dependencies installed before the agent starts.
Setup funds the account in `chain_context.json` with 10 ETH.
The verifier makes its own local fork of the sidecar after the agent stops.
It deploys the wallet fixtures through their real factories and submits a real type-4 delegation transaction.
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
| `safe_late_vote` | A Safe vote remains valid after 26 hours | "so a vote can take them a day to finish" | delay |
| `smart_wallet_new` | An undeployed Coinbase wallet's ERC-6492 signature is accepted | "many newer holders use smart wallets" | smart wallets |
| `smart_wallet_deployed` | A deployed Coinbase wallet's signature is accepted | "many newer holders use smart wallets" | smart wallets |
| `delegated_eoa` | A delegated EOA can sign with its key | "holders vote on proposals by signing" | EIP-7702 |

Each negative check also requires its matching positive check to pass.
The checks request typed data through `voteToSign`; they do not require domain names, struct names, storage, or a nonce scheme.
RewardKit reads the named records in `checks.json` and awards 1 only when every check passes.

## Why it matters

Viem's [standalone verification utility](https://github.com/wevm/viem/blob/viem%402.57.11/src/utils/signature/verifyMessage.ts#L39-L55) recovers an EOA.
Its [public client action](https://github.com/wevm/viem/blob/viem%402.57.11/src/actions/public/verifyHash.ts#L155-L197) also asks the chain.
The [siwe contract check](https://github.com/spruceid/siwe/blob/911f6f2/packages/siwe/lib/utils.ts#L22-L35) calls ERC-1271 directly, which cannot deploy an undeployed signer.
[Snapshot's verification order](https://github.com/snapshot-labs/snapshot.js/blob/v0.17.6/src/verify/evm.ts#L31-L111) reflects these distinct signing paths.

Safe [hashes the app digest inside SafeMessage](https://github.com/safe-global/safe-smart-account/blob/v1.4.1/contracts/handler/CompatibilityFallbackHandler.sol#L56-L80).
Safe{Wallet} [hands over the signature at threshold](https://github.com/safe-global/safe-wallet-monorepo/blob/d758ef1/apps/web/src/services/safe-messages/safeMsgNotifications.ts#L4-L6).
Viem [wraps undeployed smart account signatures in ERC-6492](https://github.com/wevm/viem/blob/viem@2.57.11/src/account-abstraction/accounts/toSmartAccount.ts#L113-L137).
A backend that treats every signer as an EOA rejects these holders even when their wallets sign correctly.

## Notes

This task needs `MAINNET_RPC_URL` for state at block 23,819,000.
Without it, the free check skips oracle and nop trials.
The draft empty-signature onchain approval check is excluded.
Viem 2.57.11's [ERC-6492 verifier](https://github.com/wevm/viem/blob/viem%402.57.11/contracts/src/ERC6492SignatureVerifier.sol#L71-L77) requires at least 32 signature bytes before checking ERC-1271.
Its public client action rejects `0x` even when the Safe approves that message onchain.
The checks do not enforce a particular domain or message layout.

## Trials

Not run yet.
