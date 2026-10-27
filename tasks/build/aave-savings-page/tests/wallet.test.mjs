import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import net from 'node:net';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { encodeFunctionData, hashTypedData, parseAbi, privateKeyToAccount, generatePrivateKey } from './deps.mjs';
import { POOL, USDC, erc20, pool, requestedSupplies } from './chain.mjs';
import { rpc } from './rpc.mjs';
import { injectWallet } from './wallet.mjs';

const owner = '0x1111111111111111111111111111111111111111';
const supply = { to: POOL, data: encodeFunctionData({ abi: pool, functionName: 'supply', args: [USDC, 100_000_000n, owner, 0] }) };
const approval = { to: USDC, data: encodeFunctionData({ abi: erc20, functionName: 'approve', args: [POOL, 100_000_000n] }) };

test('records a requested supply even when the wallet refused to send it', () => {
  const result = requestedSupplies([{ method: 'eth_sendTransaction', params: [supply], error: 'revert' }]);
  assert.deepEqual(result, [{ functionName: 'supply', args: ['0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48', 100_000_000n, owner, 0] }]);
});

test('finds the supply inside an atomic bundle without counting its approval', () => {
  const result = requestedSupplies([{ method: 'wallet_sendCalls', params: [{ calls: [approval, supply] }] }]);
  assert.deepEqual(result, [{ functionName: 'supply', args: ['0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48', 100_000_000n, owner, 0] }]);
  assert.deepEqual(requestedSupplies([{ method: 'eth_sendTransaction', params: [approval] }]), []);
});

test('ignores supply-shaped calldata sent to another contract', () => {
  const result = requestedSupplies([
    { method: 'eth_sendTransaction', params: [{ ...supply, to: USDC }] },
    { method: 'eth_sendTransaction', params: [supply] },
  ]);
  assert.deepEqual(result, [{ functionName: 'supply', args: ['0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48', 100_000_000n, owner, 0] }]);
});

test('recognizes the deposit alias through wallet_sendTransaction', () => {
  const data = encodeFunctionData({ abi: pool, functionName: 'deposit', args: [USDC, 6000_000_000n, owner, 0] });
  assert.deepEqual(requestedSupplies([{ method: 'wallet_sendTransaction', params: [{ to: POOL, data }] }]), [{
    functionName: 'deposit', args: [USDC, 6000_000_000n, owner, 0],
  }]);
});

test('the wallet blocks fork controls and runs non-atomic calls as separate transactions', { timeout: 30_000 }, async () => {
  const server = net.createServer();
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const port = server.address().port;
  await new Promise(resolve => server.close(resolve));
  const url = `http://127.0.0.1:${port}`;
  const anvil = spawn('anvil', ['--port', String(port), '--accounts', '0', '--chain-id', '1', '--base-fee', '0', '--silent'], { stdio: 'ignore' });
  try {
    for (let i = 0; i < 150; i++) {
      try { if (await rpc(url, 'eth_chainId') === '0x1') break; } catch { /* Wait for the test chain. */ }
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    const account = privateKeyToAccount(generatePrivateKey());
    await rpc(url, 'anvil_setBalance', [account.address, '0x100000']);
    let binding;
    const context = { exposeBinding: async (_name, handler) => { binding = handler; }, addInitScript: async () => {} };
    const state = await injectWallet(context, { account, mainRpc: url });
    const request = (method, params = []) => binding({}, { method, params });
    for (const method of ['hardhat_setBalance', 'anvil_setBalance', 'eth_sendUnsignedTransaction']) {
      const result = await request(method, [owner, '0x999']);
      assert.equal(result.code, 4200);
      assert.equal(result.message, 'RPC permits reads only');
    }
    assert.equal(await request('eth_getBalance', [owner, 'latest']), '0x0');
    assert.deepEqual(await request('wallet_getCapabilities'), { '0x1': {
      atomic: { status: 'unsupported' }, atomicBatch: { supported: false },
    } });
    const rejected = await request('wallet_sendCalls', [{ version: '2.0.0', chainId: '0x1', atomicRequired: true, calls: [{ to: owner, value: '0x1' }] }]);
    assert.equal(rejected.code, 5760);
    const result = await request('wallet_sendCalls', [{ version: '2.0.0', chainId: '0x1', atomicRequired: false,
      calls: [{ to: owner, value: '0x1' }, { to: owner, value: '0x2' }] }]);
    const status = await request('wallet_getCallsStatus', [result.id]);
    assert.deepEqual({ status: status.status, atomic: status.atomic, receipts: status.receipts.map(receipt => receipt.status) },
      { status: 200, atomic: false, receipts: ['0x1', '0x1'] });
    assert.equal(await request('eth_getBalance', [owner, 'latest']), '0x3');
    assert.equal(state.transactions.length, 2);
    const hash = await request('wallet_sendTransaction', [{ to: owner, value: '0x4' }]);
    assert.equal((await rpc(url, 'eth_getTransactionReceipt', [hash])).status, '0x1');
    assert.equal(await request('eth_getBalance', [owner, 'latest']), '0x7');
    assert.equal(state.transactions.length, 3);
  } finally {
    if (anvil.exitCode === null) { const exited = once(anvil, 'exit'); anvil.kill('SIGTERM'); await exited; }
  }
});

test('the delegated wallet validates its own permit signature and rejects another signer', { timeout: 20_000 }, async () => {
  const server = net.createServer();
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const port = server.address().port;
  await new Promise(resolve => server.close(resolve));
  const url = `http://127.0.0.1:${port}`;
  const anvil = spawn('anvil', ['--port', String(port), '--accounts', '0', '--chain-id', '1', '--silent'], { stdio: 'ignore' });
  try {
    for (let i = 0; i < 100; i++) {
      try { if (await rpc(url, 'eth_chainId') === '0x1') break; } catch { /* Wait for Anvil to bind its port. */ }
      await new Promise(resolve => setTimeout(resolve, 50));
    }
    const account = privateKeyToAccount(generatePrivateKey());
    const other = privateKeyToAccount(generatePrivateKey());
    const implementation = '0x0000000000000000000000000000000000007702';
    const code = (await fs.readFile(new URL('./wallet-bytecode.txt', import.meta.url), 'utf8')).trim();
    await rpc(url, 'anvil_setCode', [implementation, code]);
    await rpc(url, 'anvil_setCode', [account.address, `0xef0100${implementation.slice(2)}`]);
    const typed = {
      domain: { name: 'USD Coin', version: '2', chainId: 1, verifyingContract: USDC },
      types: { Permit: [
        { name: 'owner', type: 'address' }, { name: 'spender', type: 'address' },
        { name: 'value', type: 'uint256' }, { name: 'nonce', type: 'uint256' }, { name: 'deadline', type: 'uint256' },
      ] }, primaryType: 'Permit',
      message: { owner: account.address, spender: POOL, value: 100_000_000n, nonce: 0n, deadline: 2_000_000_000n },
    };
    const abi = parseAbi(['function isValidSignature(bytes32,bytes) view returns (bytes4)']);
    const call = async signature => rpc(url, 'eth_call', [{ to: account.address,
      data: encodeFunctionData({ abi, functionName: 'isValidSignature', args: [hashTypedData(typed), signature] }) }, 'latest']);
    assert.equal((await call(await account.signTypedData(typed))).slice(0, 10), '0x1626ba7e');
    assert.equal((await call(await other.signTypedData(typed))).slice(0, 10), '0xffffffff');
  } finally {
    if (anvil.exitCode === null) {
      const exited = once(anvil, 'exit');
      anvil.kill('SIGTERM');
      await exited;
    }
  }
});
