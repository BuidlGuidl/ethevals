import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import net from 'node:net';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { requireRead, walletWrites, walletIdle, pageRead } from './rpc-policy.mjs';
import { rpc } from './rpc.mjs';
import { require, parseAbi } from './deps.mjs';

test('the read policy follows the task chain and blocks unknown methods', async () => {
  const policy = JSON.parse(await fs.readFile(new URL('../../../../runner/ethevals/images/rpc_methods.json', import.meta.url), 'utf8'));
  const accepted = [];
  for (const [method, decision] of Object.entries(policy)) {
    try { requireRead(method); accepted.push(method); }
    catch (error) { assert.equal(error.message, 'RPC permits reads only'); }
    assert.equal(accepted.includes(method), decision === 'allow' && !method.startsWith('eth_send'), method);
  }
  assert.equal(accepted.includes('eth_call'), true);
  assert.throws(() => requireRead('hardhat_futureMethod'), { code: 4200, message: 'RPC permits reads only' });
});

test('cap observations count approval, alias sends, signatures and pending calls', async () => {
  const requests = ['eth_call', 'eth_sendTransaction', 'wallet_sendTransaction', 'wallet_sendCalls', 'personal_sign', 'eth_signTypedData_v4']
    .map(method => ({ method }));
  assert.deepEqual(walletWrites(requests).map(request => request.method), [
    'eth_sendTransaction', 'wallet_sendTransaction', 'wallet_sendCalls', 'personal_sign', 'eth_signTypedData_v4',
  ]);
  const wallet = { requests: [], pending: 1, lastActivity: Date.now() };
  assert.equal(await walletIdle(wallet, { idleMs: 10, timeoutMs: 20 }), false);
  wallet.pending = 0;
  assert.equal(await walletIdle(wallet, { idleMs: 10, timeoutMs: 200 }), true);
});

test('waits for a delayed wallet continuation instead of counting at five seconds', async () => {
  const wallet = { pending: 1, lastActivity: Date.now(), requests: [] };
  const continued = setTimeout(() => {
    wallet.requests.push({ method: 'wallet_sendTransaction' });
    wallet.pending = 0;
    wallet.lastActivity = Date.now();
  }, 5600);
  try {
    assert.equal(await walletIdle(wallet, { idleMs: 100, timeoutMs: 6500 }), true);
    assert.deepEqual(walletWrites(wallet.requests), [{ method: 'wallet_sendTransaction' }]);
  } finally { clearTimeout(continued); }
});

test('a page can decode a swap revert after it passes through the read proxy', async () => {
  const server = net.createServer();
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const port = server.address().port;
  await new Promise(resolve => server.close(resolve));
  const url = `http://127.0.0.1:${port}`;
  const anvil = spawn('anvil', ['--port', String(port), '--accounts', '0', '--chain-id', '1', '--silent'], { stdio: 'ignore' });
  try {
    for (let i = 0; ; i++) {
      try { await rpc(url, 'eth_chainId'); break; }
      catch (error) { if (i === 150) throw error; await new Promise(resolve => setTimeout(resolve, 100)); }
    }
    const router = '0x0000000000000000000000000000000000000a11';
    await rpc(url, 'anvil_setCode', [router, '0x6339d3549660e01b60005260046000fd']);
    const response = await pageRead(rpc, url, { id: 7, method: 'eth_call', params: [{ to: router, data: '0x' }, 'latest'] });
    assert.equal(response.id, 7);
    assert.equal(response.error.data, '0x39d35496');
    const { decodeErrorResult } = require('viem');
    assert.equal(decodeErrorResult({ abi: parseAbi(['error V3TooLittleReceived()']), data: response.error.data }).errorName,
      'V3TooLittleReceived');
    assert.deepEqual(await pageRead(rpc, url, { id: 8, method: 'anvil_mine', params: [] }),
      { jsonrpc: '2.0', id: 8, error: { code: 4200, message: 'RPC permits reads only', data: undefined } });
  } finally {
    if (anvil.exitCode === null) { const exited = once(anvil, 'exit'); anvil.kill('SIGTERM'); await exited; }
  }
});
