import test from 'node:test';
import assert from 'node:assert/strict';
import net from 'node:net';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { injectWallet } from './wallet.mjs';
import { generatePrivateKey, privateKeyToAccount } from './deps.mjs';
import { classify, ROUTERS } from './chain.mjs';
import { rpc, receipt } from './rpc.mjs';
import { until } from './harness.mjs';

test('records and rejects only the swap after an earlier fee has mined', { timeout: 30_000 }, async () => {
  const listener = net.createServer();
  await new Promise(resolve => listener.listen(0, '127.0.0.1', resolve));
  const port = listener.address().port;
  await new Promise(resolve => listener.close(resolve));
  const url = `http://127.0.0.1:${port}`;
  const child = spawn('anvil', ['--port', String(port), '--accounts', '0', '--chain-id', '1', '--base-fee', '0', '--silent'], { stdio: 'ignore' });
  try {
    assert.equal(await until(async () => await rpc(url, 'eth_chainId') === '0x1'), true);
    const account = privateKeyToAccount(generatePrivateKey());
    const treasury = '0x1111111111111111111111111111111111111111';
    await rpc(url, 'anvil_setBalance', [account.address, '0x100000']);
    let binding;
    const context = { exposeBinding: async (_name, fn) => { binding = fn; }, addInitScript: async () => {} };
    const wallet = await injectWallet(context, { account, mainRpc: url, beforeSend: async (tx, entry) => {
      entry.kind = classify(tx, treasury).kind;
      assert.equal(wallet.requests.includes(entry), true);
      if (entry.kind === 'swap') throw Object.assign(new Error('User rejected the swap request'), { code: 4001 });
    } });
    const request = (method, params) => binding({}, { method, params });
    const fee = await request('eth_sendTransaction', [{ to: treasury, value: '0x7' }]);
    assert.equal((await rpc(url, 'eth_getTransactionReceipt', [fee])).status, '0x1');
    const rejected = await request('wallet_sendTransaction', [{ to: ROUTERS.SwapRouter02, data: '0x12345678' }]);
    assert.equal(rejected.code, 4001);
    assert.equal(wallet.transactions.length, 1);
    assert.deepEqual(wallet.requests.map(entry => entry.kind), ['fee', 'swap']);
    assert.match(wallet.requests[1].error, /rejected/);
    assert.equal(await rpc(url, 'eth_getBalance', [treasury, 'latest']), '0x7');
    assert.equal((await request('hardhat_setBalance', [treasury, '0x999'])).code, 4200);
    assert.equal(wallet.pending, 0);
  } finally {
    if (child.exitCode === null) { const exited = once(child, 'exit'); child.kill('SIGTERM'); await exited; }
  }
});

test('waits for mining beyond the old ten-second receipt limit', { timeout: 30_000 }, async () => {
  const listener = net.createServer();
  await new Promise(resolve => listener.listen(0, '127.0.0.1', resolve));
  const port = listener.address().port;
  await new Promise(resolve => listener.close(resolve));
  const url = `http://127.0.0.1:${port}`;
  const child = spawn('anvil', ['--port', String(port), '--accounts', '0', '--chain-id', '1', '--base-fee', '0', '--silent'], { stdio: 'ignore' });
  let timer;
  try {
    assert.equal(await until(async () => await rpc(url, 'eth_chainId') === '0x1'), true);
    const sender = '0x1111111111111111111111111111111111111111';
    await rpc(url, 'anvil_setBalance', [sender, '0x100000']);
    await rpc(url, 'anvil_impersonateAccount', [sender]);
    await rpc(url, 'evm_setAutomine', [false]);
    const hash = await rpc(url, 'eth_sendTransaction', [{ from: sender, to: '0x2222222222222222222222222222222222222222', value: '0x1', gas: '0x5208', gasPrice: '0x0' }]);
    let mining;
    timer = setTimeout(() => { mining = rpc(url, 'evm_mine'); }, 11_500);
    assert.equal((await receipt(url, hash)).status, '0x1');
    await mining;
  } finally {
    clearTimeout(timer);
    if (child.exitCode === null) { const exited = once(child, 'exit'); child.kill('SIGTERM'); await exited; }
  }
});
