#!/bin/sh
set -eu
cd /workspace
test -r chain_context.json
test ! -r /private/private_chain_context.json
context() {
    python3 -c 'import json, sys; print(json.load(open("chain_context.json"))[sys.argv[1]])' "$1"
}
rpc=$(context rpcUrl)
key=$(context privateKey)
vault=$(context vault)
market=$(context marketId)
morpho=0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb
adapter=$(cast call "$vault" 'liquidityAdapter()(address)' --rpc-url "$rpc")
params=$(cast call "$morpho" 'idToMarketParams(bytes32)(address,address,address,address,uint256)' "$market" --rpc-url "$rpc" --json |
    python3 -c 'import json, sys; print("(" + ",".join(map(str, json.load(sys.stdin))) + ")")')
data=$(cast abi-encode 'f((address,address,address,address,uint256))' "$params")
id_data=$(cast abi-encode 'f(string,address,(address,address,address,address,uint256))' this/marketParams "$adapter" "$params")
send() {
    cast send "$vault" "$@" --private-key "$key" --rpc-url "$rpc" --json > /dev/null
}

# Submit events identify the exact calldata, including raises with different amounts.
topic=$(cast keccak 'Submit(bytes4,bytes,uint256)')
cast logs --address "$vault" --from-block 26256001 --to-block latest "$topic" --rpc-url "$rpc" --json |
    python3 -c 'import json, sys; [print(log["data"]) for log in json.load(sys.stdin)]' > /tmp/vault-submit-events
while IFS= read -r event_data; do
    pending=$(cast abi-decode 'f()(bytes,uint256)' "$event_data" --json |
        python3 -c 'import json, sys; print(json.load(sys.stdin)[0])')
    decoded=$(cast calldata-decode 'increaseAbsoluteCap(bytes,uint256)' "$pending" --json 2>/dev/null || true)
    if [ -z "$decoded" ]; then
        decoded=$(cast calldata-decode 'increaseRelativeCap(bytes,uint256)' "$pending" --json 2>/dev/null || true)
    fi
    if [ -z "$decoded" ]; then continue; fi
    pending_id=$(printf '%s' "$decoded" | python3 -c 'import json, sys; print(json.load(sys.stdin)[0])')
    if [ "$pending_id" != "$id_data" ]; then continue; fi
    executable=$(cast call "$vault" 'executableAt(bytes)(uint256)' "$pending" --rpc-url "$rpc" | awk '{print $1}')
    if [ "$executable" != 0 ]; then send 'revoke(bytes)' "$pending"; fi
done < /tmp/vault-submit-events

send 'decreaseAbsoluteCap(bytes,uint256)' "$id_data" 0
send 'decreaseRelativeCap(bytes,uint256)' "$id_data" 0

# An unset route serves deposits and withdrawals from idle assets.
send 'setLiquidityAdapterAndData(address,bytes)' 0x0000000000000000000000000000000000000000 0x
pass=0
while [ "$pass" -lt 5 ]; do
    assets=$(cast call "$adapter" 'expectedSupplyAssets(bytes32)(uint256)' "$market" --rpc-url "$rpc" | awk '{print $1}')
    if [ "$assets" = 0 ]; then break; fi
    send 'deallocate(address,bytes,uint256)' "$adapter" "$data" "$assets"
    pass=$((pass + 1))
done
test "$(cast call "$adapter" 'expectedSupplyAssets(bytes32)(uint256)' "$market" --rpc-url "$rpc" | awk '{print $1}')" = 0
echo 'Revoked pending raises, zeroed both market caps, removed the liquidity route, and moved the market assets to idle.'
