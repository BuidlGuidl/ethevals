#!/bin/bash
set -euo pipefail
# Read only chain.json. The reference has the same filtered RPC and signing key as the agent.
read_value() { sed -n 's/.*"'"$1"'": "\([^"]*\)".*/\1/p' /workspace/chain.json; }
rpc=$(read_value rpc_url)
token=$(read_value token)
recipient=$(read_value recipient)
key=$(read_value private_key)
# Read decimals on-chain so the human amount becomes the token's exact base-unit amount.
decimals=$(cast call "$token" 'decimals()(uint8)' --rpc-url "$rpc")
amount=$((125 * 10 ** decimals / 10))
# Sign locally and submit one raw transaction; cast waits for its receipt before returning.
cast send "$token" 'transfer(address,uint256)' "$recipient" "$amount" --private-key "$key" --rpc-url "$rpc"
