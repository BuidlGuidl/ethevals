import fs from 'node:fs/promises';
import path from 'node:path';
import net from 'node:net';
import { spawn } from 'node:child_process';
import { chromium, privateKeyToAccount, generatePrivateKey } from './deps.mjs';
import { rpc, fundWallet } from './rpc.mjs';
import { injectWallet } from './wallet.mjs';
import { requireRead, walletIdle } from './rpc-policy.mjs';
import { serveBuild } from './static-server.mjs';

export async function until(fn, timeout = 20_000) {
  const deadline = Date.now() + timeout;
  let lastError;
  do {
    try { const result = await fn(); if (result) return result; } catch (error) { lastError = error; }
    await new Promise(resolve => setTimeout(resolve, 200));
  } while (Date.now() < deadline);
  if (lastError) throw lastError;
  return false;
}

// All callbacks and funding data come from verifier-owned task files.
export async function createHarness({ workspace, output, sourceContext = '/chain/chain_context.json', funding, prepare = async () => {}, warm }) {
  const processes = [];
  let browser;
  let preview;
  let active;
  const stringify = data => JSON.stringify(data, (_, value) => typeof value === 'bigint' ? value.toString() : value, 2);
  const saveJson = (name, data) => fs.writeFile(path.join(output, name), stringify(data) + '\n');
  async function capture(session, name) {
    await walletIdle(session.wallet);
    await fs.writeFile(path.join(output, `${name}-page.txt`), await session.page.locator('body').innerText());
    await fs.writeFile(path.join(output, `${name}-page.html`), await session.page.content());
    await session.page.screenshot({ path: path.join(output, `${name}.png`), fullPage: true });
    await saveJson(`${name}-wallet.json`, { requests: session.wallet.requests, transactions: session.wallet.transactions });
  }
  async function port() {
    const server = net.createServer();
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    const number = server.address().port;
    await new Promise(resolve => server.close(resolve));
    return number;
  }
  function start(command, args, cwd, logfile) {
    const child = spawn(command, args, { cwd, stdio: ['ignore', 'pipe', 'pipe'], detached: true });
    const log = [];
    child.stdout.on('data', data => log.push(data));
    child.stderr.on('data', data => log.push(data));
    child.on('error', error => log.push(Buffer.from(error.message)));
    processes.push({ child, log, logfile });
    return child;
  }


  async function close() {
    if (browser) await browser.close().catch(() => {});
    if (preview) await new Promise(resolve => preview.close(resolve));
    for (const { child, log, logfile } of processes.reverse()) {
      try { process.kill(-child.pid, 'SIGTERM'); } catch { /* Already exited. */ }
      await fs.writeFile(path.join(output, logfile), Buffer.concat(log));
    }
  }
  try {
    const { rpcUrl: source, chainId } = JSON.parse(await fs.readFile(sourceContext, 'utf8'));
    const forkPort = await port();
    const serverPort = await port();
    const mainRpc = 'http://127.0.0.1:' + forkPort;
    const sourceBlock = await rpc(source, 'eth_blockNumber');
    start('anvil', ['--host', '127.0.0.1', '--port', String(forkPort), '--accounts', '0', '--chain-id', String(chainId),
      '--base-fee', '0', '--prune-history', '1', '--silent', '--fork-url', source, '--fork-block-number', String(Number(sourceBlock))], workspace, 'fork.log');
    if (!await until(async () => await rpc(mainRpc, 'eth_chainId') === '0x' + chainId.toString(16), 30_000)) throw new Error('Verifier fork did not start');
    await rpc(mainRpc, 'anvil_setBlockTimestampInterval', [0]);
    await prepare(mainRpc);
    const account = privateKeyToAccount(generatePrivateKey());
    await fundWallet(mainRpc, account, funding);
    await warm?.(mainRpc, account);
    let snapshot = await rpc(mainRpc, 'evm_snapshot');
    async function reset() {
      if (active) { await active.context.close(); active = null; }
      if (!await rpc(mainRpc, 'evm_revert', [snapshot])) throw Object.assign(new Error('Fork snapshot restore failed'), { infrastructure: true });
      snapshot = await rpc(mainRpc, 'evm_snapshot');
    }
    try { preview = await serveBuild(workspace, serverPort); }
    catch (error) { error.pageFailure = true; throw error; }
    const origin = 'http://127.0.0.1:' + serverPort;
    const libraryDirs = ['/root/voting-libs/usr/lib/x86_64-linux-gnu', '/root/voting-libs/usr/lib/aarch64-linux-gnu',
      '/root/voting-libs/lib/x86_64-linux-gnu', '/root/voting-libs/lib/aarch64-linux-gnu'];
    // The preflight cannot see libraries passed only to the browser child.
    process.env.PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS = '1';
    browser = await chromium.launch({ headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage'],
      env: { ...process.env, LD_LIBRARY_PATH: libraryDirs.join(':'), FONTCONFIG_FILE: '/root/voting-fonts.conf' } });
    async function session({ beforeSend, account: sessionAccount = account } = {}) {
      if (active) await active.context.close();
      const context = await browser.newContext({ viewport: { width: 1440, height: 1100 }, serviceWorkers: 'block' });
      // Fulfill every browser JSON-RPC request, including /rpc proxies and chain:8545.
      await context.route('**/*', async route => {
        const request = route.request();
        const headers = { 'access-control-allow-origin': '*', 'access-control-allow-headers': '*', 'access-control-allow-methods': 'POST, OPTIONS', 'access-control-allow-private-network': 'true' };
        if (request.method() === 'OPTIONS') return route.fulfill({ status: 204, headers });
        let payload;
        try { payload = request.postDataJSON(); } catch { /* Static files have no JSON body. */ }
        if (!payload || !(Array.isArray(payload) ? payload.every(item => typeof item.method === 'string') : typeof payload.method === 'string')) {
          return request.url().startsWith(origin + '/') ? route.continue() : route.abort();
        }
        const dispatch = async item => {
          try {
            // Page reads see the fork. Writes and chain controls belong to the wallet only.
            requireRead(item.method);
            return { jsonrpc: '2.0', id: item.id, result: await rpc(mainRpc, item.method, item.params || []) };
          } catch (error) { return { jsonrpc: '2.0', id: item.id, error: { code: error.code || -32603, message: error.message, data: error.data } }; }
        };
        const result = Array.isArray(payload) ? await Promise.all(payload.map(dispatch)) : await dispatch(payload);
        await route.fulfill({ status: 200, contentType: 'application/json', headers, body: stringify(result) });
      });
      await context.routeWebSocket('**/*', socket => socket.close());

      const wallet = await injectWallet(context, { account: sessionAccount, mainRpc, beforeSend, chainId });
      const page = await context.newPage();
      page.setDefaultTimeout(5000);
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      active = { page, context, wallet, errors };
      await page.goto(origin, { waitUntil: 'domcontentloaded' });
      return active;
    }
    return { mainRpc, account, sourceBlock, session, reset, capture, close, get active() { return active; } };
  } catch (error) {
    await close();
    throw error;
  }
}
