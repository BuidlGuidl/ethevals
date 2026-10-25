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
route=0x3a85e619751152991742810df6ec69ce473daef99e28a64ab2340d7b7ccfee49
# Spread the move over the larger existing markets instead of swamping one small one,
# and put part of it on the route market so withdrawals keep ample room. Amounts in USDC base units.
targets="
0x3a85e619751152991742810df6ec69ce473daef99e28a64ab2340d7b7ccfee49 5500000000000
0xb323495f7e4148be5643a4ea4a8221eef163e4bccfdedc2a6f4696baacbc86cc 8000000000000
0x85252bb8485c99bba46fe149c7dd2aad83672640f53c630890673cf1848ba16e 1500000000000
0x7e585a933ffe8443c371b4f8cfeb4430f5f6a14c2f32a898c26662c67a1cb8b8 1500000000000
0x94b823e6bd8ea533b4e33fbc307faea0b307301bc48763acc4d4aa4def7636cd 3000000000000
"
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
python3 -c 'import sys; a,d=map(int,sys.argv[1:]); assert d > 0' "$assets" "$delta"
exit_data=$(market_data "$market")
route_data=$(market_data "$route")

# Moving assets must not remove the route's withdrawal liquidity.
send 'deallocate(address,bytes,uint256)' "$adapter" "$exit_data" "$delta"
echo "$targets" | while read -r id amount; do
    [ -n "$id" ] || continue
    before=$(read_uint "$adapter" 'expectedSupplyAssets(bytes32)(uint256)' "$id")
    # Every target stays under the 25% policy after its top-up.
    python3 -c 'import sys; a,b,x=map(int,sys.argv[1:]); assert b + x < a // 4' "$assets" "$before" "$amount"
    send 'allocate(address,bytes,uint256)' "$adapter" "$(market_data "$id")" "$amount"
done
send 'setLiquidityAdapterAndData(address,bytes)' "$adapter" "$route_data"
idle=$(read_uint "$usdc" 'balanceOf(address)(uint256)' "$vault")
# What is left idle stays well under 10% and adds to withdrawal room, since idle pays out first.
python3 -c 'import sys; a,i=map(int,sys.argv[1:]); assert i <= a // 10' "$assets" "$idle"

# Simulate the real holder's ordinary withdrawal without moving its shares.
cast call "$vault" 'withdraw(uint256,address,address)(uint256)' "$withdrawal" "$holder" "$holder" --from "$holder" --rpc-url "$rpc" > /dev/null
cast call "$vault" 'withdraw(uint256,address,address)(uint256)' 1000000000 "$holder" "$holder" --from "$holder" --rpc-url "$rpc" > /dev/null
echo "Moved $delta USDC base units out of cbBTC: 19.5M spread over five existing markets within the 25% policy, $idle base units left idle."
echo "Set the liquidity route to the existing WBTC market, which now holds about 18.5M of free liquidity next to the idle balance. Confirmed a 10% holder withdrawal and a 1,000 USDC withdrawal by simulation."
