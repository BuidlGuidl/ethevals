holders vote on proposals by signing, and our backend stores each vote if it's valid. big holders vote
from a 2-of-3 Safe, so a vote can take them a day or two to finish. many newer holders use smart wallets.
in src/votes.ts, export voteToSign({ proposalId, voter, support }), returning the typed data the voter
signs, and checkVote({ proposalId, voter, support }, signature), resolving to true if we should store the vote. we're on
mainnet; the RPC URL is in RPC_URL.

proposalId is a bigint, voter is an address, and support is 0, 1, or 2 (against, for, abstain).
voteToSign can be async. Its result is the object that viem's signTypedData takes.
checkVote receives those vote fields and a hex signature, and resolves to a boolean.
