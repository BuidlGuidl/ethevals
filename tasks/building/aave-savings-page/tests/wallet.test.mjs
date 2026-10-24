import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import net from 'node:net';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { encodeFunctionData, hashTypedData, parseAbi, privateKeyToAccount, generatePrivateKey } from './deps.mjs';
import { POOL, USDC, erc20, pool, rpc } from './chain.mjs';
import { requestedSupplies } from './wallet.mjs';

const owner = '0x1111111111111111111111111111111111111111';
const supply = { to: POOL, data: encodeFunctionData({ abi: pool, functionName: 'supply', args: [USDC, 100_000_000n, owner, 0] }) };
const approval = { to: USDC, data: encodeFunctionData({ abi: erc20, functionName: 'approve', args: [POOL, 100_000_000n] }) };

test('records a requested supply even when the wallet refused to send it', () => {
  const result = requestedSupplies([{ method: 'eth_sendTransaction', params: [supply], chainId: 11155111, error: 'revert' }]);
  assert.deepEqual(result, [{ functionName: 'supply', args: ['0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48', 100_000_000n, owner, 0], chainId: 11155111 }]);
});

test('finds the supply inside an atomic bundle without counting its approval', () => {
  const result = requestedSupplies([{ method: 'wallet_sendCalls', params: [{ calls: [approval, supply] }], chainId: 1 }]);
  assert.deepEqual(result, [{ functionName: 'supply', args: ['0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48', 100_000_000n, owner, 0], chainId: 1 }]);
  assert.deepEqual(requestedSupplies([{ method: 'eth_sendTransaction', params: [approval], chainId: 1 }]), []);
});

test('ignores supply-shaped calldata sent to another contract', () => {
  const result = requestedSupplies([
    { method: 'eth_sendTransaction', params: [{ ...supply, to: USDC }], chainId: 1 },
    { method: 'eth_sendTransaction', params: [supply], chainId: 1 },
  ]);
  assert.deepEqual(result, [{ functionName: 'supply', args: ['0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48', 100_000_000n, owner, 0], chainId: 1 }]);
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
