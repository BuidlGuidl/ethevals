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
idle=0x54efdee08e272e929034a8f26f7ca34b1ebe364b275391169b28c6d7db24dbc8

params() {
    cast call "$morpho" 'idToMarketParams(bytes32)(address,address,address,address,uint256)' "$1" --rpc-url "$rpc" --json |
        python3 -c 'import json, sys; print("(" + ",".join(map(str, json.load(sys.stdin))) + ")")'
}
send() {
    cast send "$vault" "$@" --private-key "$key" --rpc-url "$rpc" --json > /dev/null
}
source_params=$(params "$market")
idle_params=$(params "$idle")
send 'submitCap((address,address,address,address,uint256),uint256)' "$source_params" 0
max=115792089237316195423570985008687907853269984665640564039457584007913129639935
send 'reallocate(((address,address,address,address,uint256),uint256)[])' "[($source_params,0),($idle_params,$max)]"

supply=''
length=$(cast call "$vault" 'supplyQueueLength()(uint256)' --rpc-url "$rpc")
i=0
while [ "$i" -lt "$length" ]; do
    id=$(cast call "$vault" 'supplyQueue(uint256)(bytes32)' "$i" --rpc-url "$rpc")
    if [ "$id" != "$market" ]; then supply="${supply}${supply:+,}$id"; fi
    i=$((i + 1))
done
send 'setSupplyQueue(bytes32[])' "[$supply]"

indexes=''
length=$(cast call "$vault" 'withdrawQueueLength()(uint256)' --rpc-url "$rpc")
i=0
while [ "$i" -lt "$length" ]; do
    id=$(cast call "$vault" 'withdrawQueue(uint256)(bytes32)' "$i" --rpc-url "$rpc")
    if [ "$id" != "$market" ]; then indexes="${indexes}${indexes:+,}$i"; fi
    i=$((i + 1))
done
send 'updateWithdrawQueue(uint256[])' "[$indexes]"
