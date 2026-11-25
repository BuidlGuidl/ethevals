"""Callback-only simulation (ownerless Raffle): the raffle is deployed and mid-draw (state overrides); one tx runs the VRF callback with `gas`."""
import json,urllib.request,subprocess
def cast(*a): return subprocess.run(["cast",*a],capture_output=True,text=True).stdout.strip()
d=json.load(open("out.json"))["contracts"]
F=d["src/Harness.sol:FakeCoordinator"]["bin-runtime"]
RT=json.load(open("layout.json"))["contracts"]["src/Raffle.sol:Raffle"]["bin-runtime"]
C="0x9DdfaCa8183c41ad55329BdeeD9F6A8d53168B1B"; R="0x00000000000000000000000000000000000Faff1"
URL={"sepolia":"https://ethereum-sepolia-rpc.publicnode.com","mainnet":"https://ethereum-rpc.publicnode.com"}
w=lambda v: "0x"+format(v,"064x")
def state(round_):
    # layout: 0 round, 1 roundStart, 2 players, 3 drawing, 4 pendingRequest, 5 winnings
    s={w(0):w(round_), w(1):w(1_760_000_000), w(3):w(1), w(4):w(7)}
    arr=cast("index","uint256",str(round_),"2"); s[arr]=w(5)
    base=int(cast("keccak",arr),16)
    for i in range(5): s[w(base+i)]=w(0xB0B0+i)
    return s
def sim(net,g,round_=0):
    data=cast("calldata","fulfill(address,uint256)",R,str(g))
    q=urllib.request.Request(URL[net],json.dumps({"jsonrpc":"2.0","id":1,"method":"eth_call","params":[{"from":"0x000000000000000000000000000000000000bEEF","to":C,"data":data,"gas":hex(1_000_000)},"latest",{C:{"code":"0x"+F},R:{"code":"0x"+RT,"balance":hex(5*10**16),"stateDiff":state(round_)}}]}).encode(),{"content-type":"application/json","user-agent":"curl/8"})
    r=json.load(urllib.request.urlopen(q)); return bool(int(r["result"],16))
def threshold(net,lo,hi,round_=0):
    while hi-lo>100:
        m=(lo+hi)//2
        if sim(net,m,round_): hi=m
        else: lo=m
    return hi
for rnd in (0,4):
    print(f"round {rnd}: callback with 100,000 -> sepolia ok={sim('sepolia',100000,rnd)} mainnet ok={sim('mainnet',100000,rnd)}; needs sepolia ~{threshold('sepolia',100000,400000,rnd)} mainnet ~{threshold('mainnet',20000,100000,rnd)}")
