import test from 'node:test';
import assert from 'node:assert/strict';
import net from 'node:net';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { mutationQueue } from './rpc-policy.mjs';

test('a failed market snapshot cannot remove a queued wallet transaction', async () => {
  const listener = net.createServer();
  await new Promise(resolve => listener.listen(0, '127.0.0.1', resolve));
  const port = listener.address().port;
  await new Promise(resolve => listener.close(resolve));
  const child = spawn('anvil', ['--port', String(port), '--base-fee', '0', '--silent'], { stdio: 'ignore' });
  const rpc = async (method, params = []) => {
    const response = await fetch(`http://127.0.0.1:${port}`, { method: 'POST',
      headers: { 'content-type': 'application/json' }, body: JSON.stringify({ jsonrpc: '2.0', id: 1, method, params }) });
    const result = await response.json();
    if (result.error) throw new Error(result.error.message);
    return result.result;
  };
  try {
    for (let i = 0; ; i++) {
      try { await rpc('eth_chainId'); break; }
      catch (error) { if (i === 100) throw error; await new Promise(resolve => setTimeout(resolve, 20)); }
    }
    const [from, to] = await rpc('eth_accounts');
    const send = () => rpc('eth_sendTransaction', [{ from, to, value: '0x1', gas: '0x5208', gasPrice: '0x0' }]);
    const snapshot = await rpc('evm_snapshot');
    const lost = await send();
    assert.equal((await rpc('eth_getTransactionReceipt', [lost])).status, '0x1');
    assert.equal(await rpc('evm_revert', [snapshot]), true);
    assert.equal(await rpc('eth_getTransactionByHash', [lost]), null);

    const mutate = mutationQueue();
    let captured, release;
    const capturedSnapshot = new Promise(resolve => { captured = resolve; });
    const rollback = new Promise(resolve => { release = resolve; });
    const market = mutate(async () => {
      const before = await rpc('evm_snapshot');
      captured();
      await rollback;
      await rpc('evm_revert', [before]);
      throw new Error('The market move failed.');
    });
    await capturedSnapshot;
    let sent = false;
    const wallet = mutate(async () => { sent = true; return send(); });
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(sent, false);
    release();
    await assert.rejects(market, /market move failed/);
    const retained = await wallet;
    assert.equal((await rpc('eth_getTransactionByHash', [retained])).hash, retained);
    assert.equal((await rpc('eth_getTransactionReceipt', [retained])).status, '0x1');
  } finally {
    child.kill('SIGTERM');
    await once(child, 'exit');
  }
});
