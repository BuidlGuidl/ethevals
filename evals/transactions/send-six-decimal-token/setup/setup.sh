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

# Only setup reaches the unfiltered RPC. Fund gas without giving the agent chain controls.
for address in "$sender" "$deployer"; do
    cast rpc --rpc-url "$RPC_URL" anvil_setBalance "$address" 0x8ac7230489e80000 >/dev/null
done
# Deploy a six-decimal token with its supply held by the agent's fresh sender key.
token=$(forge create setup/Token.sol:Token --use "$SOLC" --broadcast --json \
    --rpc-url "$RPC_URL" --private-key "$deployer_key" --constructor-args "$sender" | jq -r .deployedTo)

# chain.json gives the agent its signing key and the filtered RPC for reads and signed sends.
public=$(jq -n --arg rpc_url "$PUBLIC_RPC_URL" --arg private_key "$key" --arg sender "$sender" \
    --arg recipient "$recipient" --arg token "$token" '$ARGS.named')
# Keep the original addresses in /eval/private.json, outside the agent's writable workspace.
printf '%s\n' "$public" > private.json
# Only this files mapping reaches the workspace. The deployer's key stays inside setup.
jq -n --arg chain "$public" '{files: {"chain.json": $chain}}'
