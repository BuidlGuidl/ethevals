import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import { requireRead, walletWrites, walletIdle } from './rpc-policy.mjs';

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
