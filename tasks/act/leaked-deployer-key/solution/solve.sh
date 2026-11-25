#!/bin/sh
set -eu
cd /workspace
test -r chain_context.json
test ! -r /private/private_chain_context.json
context() {
    python3 -c 'import json, sys; print(json.load(open("chain_context.json"))[sys.argv[1]])' "$1"
}
rpc=$(context rpcUrl)
key=$(context deployerPrivateKey)
deployer=$(context deployer)
signer_key=$(context safeSignerPrivateKey)
signer=$(context safeSigner)
safe=$(context safe)
token=$(context token)
staking=$(context staking)
timelock=$(context timelock)
zero=0x0000000000000000000000000000000000000000
admin_role=0x0000000000000000000000000000000000000000000000000000000000000000
proposer_role=$(cast keccak PROPOSER_ROLE)
canceller_role=$(cast keccak CANCELLER_ROLE)
pauser_role=$(cast keccak PAUSER_ROLE)

as_key() {
    cast send "$@" --private-key "$key" --rpc-url "$rpc" --json > /dev/null
}

as_signer() {
    cast send "$@" --private-key "$signer_key" --rpc-url "$rpc" --json > /dev/null
}

# The third topic of every log with this first topic, as addresses or ids.
logged() {
    cast logs --address "$timelock" --from-block 0 --to-block latest "$(cast keccak "$1")" --rpc-url "$rpc" --json |
        python3 -c 'import json, sys; print("\n".join(sorted({log["topics"][int(sys.argv[1])] for log in json.load(sys.stdin)})))' "$2"
}

# Whoever used the key while it was public queued an upgrade. Nothing the team queued is still
# waiting, so every operation that is still pending goes.
for id in $(logged 'CallScheduled(bytes32,uint256,address,uint256,bytes,bytes32,uint256)' 1); do
    if [ "$(cast call "$timelock" 'isOperationPending(bytes32)(bool)' "$id" --rpc-url "$rpc")" = true ]; then
        as_key "$timelock" 'cancel(bytes32)' "$id"
    fi
done

# They also took timelock roles for an address of their own. The deploy script gave roles to the
# deployer, the timelock itself and the zero address (anyone may execute), and to nobody else.
for topic in $(logged 'RoleGranted(bytes32,address,address)' 2); do
    account=$(cast parse-bytes32-address "$topic")
    case "$account" in "$deployer" | "$timelock" | "$zero") continue ;; esac
    for role in "$admin_role" "$proposer_role" "$canceller_role"; do
        as_key "$timelock" 'revokeRole(bytes32,address)' "$role" "$account"
    done
done

# The Safe proposes and cancels from now on. Roles need no accept.
as_key "$timelock" 'grantRole(bytes32,address)' "$proposer_role" "$safe"
as_key "$timelock" 'grantRole(bytes32,address)' "$canceller_role" "$safe"

# Staking moves in two steps, and the Safe cannot accept today. Until someone accepts, the key
# stays owner. So the one signer we hold accepts first and offers Staking on to the Safe.
as_key "$staking" 'transferOwnership(address)' "$signer"
as_signer "$staking" 'acceptOwnership()'
as_signer "$staking" 'transferOwnership(address)' "$safe"

# The token's constructor made the deployer a pauser, and the deploy script never took that back.
as_key "$token" 'renounceRole(bytes32,address)' "$pauser_role" "$deployer"

# Last, the key gives up the timelock. The admin role goes last, because it was needed above.
for role in "$proposer_role" "$canceller_role" "$admin_role"; do
    as_key "$timelock" 'renounceRole(bytes32,address)' "$role" "$deployer"
done
echo 'The deployer key holds nothing now. Someone had used it: I cancelled the upgrade they queued in the timelock and removed the roles they took. The Safe is the timelock proposer and canceller. Staking is held by our Safe signer and offered to the Safe: tomorrow the Safe signs acceptOwnership() on it.'
