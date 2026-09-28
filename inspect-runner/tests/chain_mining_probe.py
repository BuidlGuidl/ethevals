import json
import subprocess
import sys
import time
sys.path.insert(0, '/opt')
from rpc_filter import Chain, rpc

key = '0x' + '11' * 32
sender = subprocess.check_output(['cast', 'wallet', 'address', '--private-key', key], text=True).strip()
target = '0x' + '22' * 20
rpc('anvil_setBalance', [sender, hex(10**20)])
rpc('anvil_setCode', [target, '0x5b600056'])
raw = subprocess.check_output(['cast', 'mktx', target, '--private-key', key, '--legacy', '--chain-id', '31337', '--nonce', '0', '--gas-limit', '30000000', '--gas-price', '2000000000'], text=True).strip()
chain = Chain()
tx = chain.forward({'jsonrpc':'2.0', 'id':1, 'method':'eth_sendRawTransaction', 'params':[raw]})
started = time.monotonic()
block = chain.freeze()
elapsed = time.monotonic() - started
before = rpc('eth_getBlockByNumber', ['latest', False])['hash']
nonce = rpc('eth_getTransactionCount', [sender, 'latest'])
balance = rpc('eth_getBalance', [sender, 'latest'])
time.sleep(2)
after = rpc('eth_getBlockByNumber', ['latest', False])['hash']
print(json.dumps(dict(tx=tx, boundary=block, before=before, after=after, nonce=nonce, balance=balance, seconds=elapsed)), flush=True)
assert block == before == after
assert rpc('eth_getTransactionCount', [sender, 'latest']) == nonce
assert rpc('eth_getBalance', [sender, 'latest']) == balance
