import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import net from 'node:net';
import os from 'node:os';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { createHarness, until } from './harness.mjs';
import { rpc } from './rpc.mjs';

test('copied harness serves another page and isolates both RPC paths', { timeout: 40_000 }, async () => {
  const listener = net.createServer();
  await new Promise(resolve => listener.listen(0, '127.0.0.1', resolve));
  const port = listener.address().port;
  await new Promise(resolve => listener.close(resolve));
  const source = `http://127.0.0.1:${port}`;
  const anvil = spawn('anvil', ['--port', String(port), '--accounts', '0', '--chain-id', '1', '--base-fee', '0', '--silent'], { stdio: 'ignore' });
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), 'page-harness-'));
  let harness;
  try {
    await until(async () => await rpc(source, 'eth_chainId') === '0x1');
    const workspace = path.join(directory, 'project');
    const output = path.join(directory, 'evidence');
    await fs.mkdir(path.join(workspace, 'dist'), { recursive: true });
    await fs.mkdir(output);
    await fs.writeFile(path.join(workspace, 'dist/index.html'), '<h1>Another page task</h1>');
    await fs.writeFile(path.join(workspace, 'chain_context.json'), '{"rpcUrl":"http://untrusted.invalid"}');
    await fs.writeFile(path.join(workspace, 'vite.config.mjs'), 'throw new Error("Agent configuration must not run")');
    const sourceContext = path.join(directory, 'trusted-context.json');
    await fs.writeFile(sourceContext, JSON.stringify({ rpcUrl: source }));
    harness = await createHarness({ workspace, output, sourceContext, funding: { nativeBalance: 1000n, transfers: [] } });
    const session = await harness.session();
    assert.equal(await session.page.locator('h1').innerText(), 'Another page task');
    const observed = await session.page.evaluate(async ({ address, endpoint }) => {
      const payload = { jsonrpc: '2.0', id: 1, method: 'hardhat_setBalance', params: [address, '0x999'] };
      const http = await fetch(endpoint, { method: 'POST', body: JSON.stringify(payload), headers: { 'content-type': 'application/json' } }).then(response => response.json());
      const wallet = await ethereum.request(payload).catch(error => ({ code: error.code, message: error.message }));
      const balance = await ethereum.request({ method: 'eth_getBalance', params: [address, 'latest'] });
      return { http: http.error.code, wallet: wallet.code, balance };
    }, { address: harness.account.address, endpoint: harness.mainRpc });
    assert.deepEqual(observed, { http: 4200, wallet: 4200, balance: '0x3e8' });
    const receiver = '0x1111111111111111111111111111111111111111';
    await session.page.evaluate(async to => ethereum.request({ method: 'wallet_sendTransaction', params: [{ to, value: '0x7' }] }), receiver);
    assert.equal(await rpc(harness.mainRpc, 'eth_getBalance', [receiver, 'latest']), '0x7');
    await harness.reset();
    assert.equal(await rpc(harness.mainRpc, 'eth_getBalance', [receiver, 'latest']), '0x0');
    assert.equal(await rpc(harness.mainRpc, 'eth_getBalance', [harness.account.address, 'latest']), '0x3e8');
    const failure = await createHarness({ workspace, output, sourceContext: path.join(directory, 'missing-context'), funding: { nativeBalance: 0n, transfers: [] } }).catch(error => error);
    assert.equal(failure.code, 'ENOENT');
  } finally {
    if (harness) await harness.close();
    if (anvil.exitCode === null) { const exited = once(anvil, 'exit'); anvil.kill('SIGTERM'); await exited; }
    await fs.rm(directory, { recursive: true, force: true });
  }
});
