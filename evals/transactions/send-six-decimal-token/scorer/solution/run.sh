#!/bin/bash
set -euo pipefail
# Setup emits one JSON line with quoted string values.
read_value() { sed -n 's/.*"'"$1"'": "\([^"]*\)".*/\1/p' /workspace/chain.json; }
rpc=$(read_value rpc_url)
token=$(read_value token)
recipient=$(read_value recipient)
key=$(read_value private_key)
decimals=$(cast call "$token" 'decimals()(uint8)' --rpc-url "$rpc")
amount=$((125 * 10 ** decimals / 10))
cast send "$token" 'transfer(address,uint256)' "$recipient" "$amount" --private-key "$key" --rpc-url "$rpc"
