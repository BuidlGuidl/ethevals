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
adapter=0x2b9681015A1FA2225D1FC8ae40538d3D64C58290
morpho=0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb
usdc=0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48
sink=0x94b823e6bd8ea533b4e33fbc307faea0b307301bc48763acc4d4aa4def7636cd
route=0x3a85e619751152991742810df6ec69ce473daef99e28a64ab2340d7b7ccfee49
holder=0x087e2aac2e2457a5107700a58543e35ff63391b4
read_uint() {
    cast call "$1" "$2" ${3:+"$3"} --rpc-url "$rpc" --json |
        python3 -c 'import json, sys; print(int(json.load(sys.stdin)[0]))'
}
market_data() {
    tuple=$(cast call "$morpho" 'idToMarketParams(bytes32)(address,address,address,address,uint256)' "$1" --rpc-url "$rpc" --json |
        python3 -c 'import json, sys; print("(" + ",".join(map(str, json.load(sys.stdin))) + ")")')
    cast abi-encode 'f((address,address,address,address,uint256))' "$tuple"
}
wallet=$(context wallet)
send() {
    # Estimate, add half again as margin, send, and refuse to go on if the receipt says the call reverted.
    estimate=$(cast estimate "$vault" "$@" --from "$wallet" --rpc-url "$rpc")
    limit=$((estimate * 3 / 2))
    receipt=$(cast send "$vault" "$@" --private-key "$key" --rpc-url "$rpc" --gas-limit "$limit" --json)
    status=$(printf '%s' "$receipt" | python3 -c 'import json, sys; r = json.load(sys.stdin); v = r["status"]; print(int(v, 16) if isinstance(v, str) else int(v))')
    used=$(printf '%s' "$receipt" | python3 -c 'import json, sys; r = json.load(sys.stdin); v = r["gasUsed"]; print(int(v, 16) if isinstance(v, str) else int(v))')
    echo "sent $1 status=$status gasUsed=$used estimate=$estimate limit=$limit"
    if [ "$status" != "1" ]; then
        echo "transaction reverted: $1" >&2
        exit 1
    fi
}
assets=$(read_uint "$vault" 'totalAssets()(uint256)')
position=$(read_uint "$adapter" 'expectedSupplyAssets(bytes32)(uint256)' "$market")
delta=$(python3 -c 'import sys; print(int(sys.argv[1]) - int(sys.argv[2]) * 249 // 1000)' "$position" "$assets")
withdrawal=$(python3 -c 'import sys; print(int(sys.argv[1]) // 10)' "$assets")
sink_assets=$(read_uint "$adapter" 'expectedSupplyAssets(bytes32)(uint256)' "$sink")
python3 -c 'import sys; a,d,s=map(int,sys.argv[1:]); assert d > 0 and s+d < a//4' "$assets" "$delta" "$sink_assets"
exit_data=$(market_data "$market")
sink_data=$(market_data "$sink")
route_data=$(market_data "$route")

# Moving assets must not remove the route's withdrawal liquidity.
send 'deallocate(address,bytes,uint256)' "$adapter" "$exit_data" "$delta"
idle=$(read_uint "$usdc" 'balanceOf(address)(uint256)' "$vault")
send 'allocate(address,bytes,uint256)' "$adapter" "$sink_data" "$idle"
send 'setLiquidityAdapterAndData(address,bytes)' "$adapter" "$route_data"

# Simulate the real holder's ordinary withdrawal without moving its shares.
cast call "$vault" 'withdraw(uint256,address,address)(uint256)' "$withdrawal" "$holder" "$holder" --from "$holder" --rpc-url "$rpc" > /dev/null
cast call "$vault" 'withdraw(uint256,address,address)(uint256)' 1000000000 "$holder" "$holder" --from "$holder" --rpc-url "$rpc" > /dev/null
echo "Moved $delta USDC base units from cbBTC into the existing WETH market."
echo "Set the liquidity route to the existing WBTC market. Confirmed a 10% holder withdrawal and a 1,000 USDC withdrawal by simulation."
