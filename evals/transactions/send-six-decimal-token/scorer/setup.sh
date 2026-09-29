#!/bin/bash
set -euo pipefail

# Each epoch uses fresh keys, so the agent cannot guess the deployer's key.
sender_wallet=$(cast wallet new --json)
deployer_wallet=$(cast wallet new --json)
key=$(jq -r '.[0].private_key' <<< "$sender_wallet")
sender=$(jq -r '.[0].address' <<< "$sender_wallet")
deployer_key=$(jq -r '.[0].private_key' <<< "$deployer_wallet")
deployer=$(jq -r '.[0].address' <<< "$deployer_wallet")
recipient=$(cast wallet new --json | jq -r '.[0].address')

for address in "$sender" "$deployer"; do
    cast rpc --rpc-url "$RPC_URL" anvil_setBalance "$address" 0x8ac7230489e80000 >/dev/null
done
token=$(forge create scorer/Token.sol:Token --use "$SOLC" --broadcast --json \
    --rpc-url "$RPC_URL" --private-key "$deployer_key" --constructor-args "$sender" | jq -r .deployedTo)

public=$(jq -n --arg rpc_url "$PUBLIC_RPC_URL" --arg private_key "$key" --arg sender "$sender" \
    --arg recipient "$recipient" --arg token "$token" '$ARGS.named')
printf '%s\n' "$public" > private.json
jq -n --arg chain "$public" '{files: {"chain.json": $chain}}'
