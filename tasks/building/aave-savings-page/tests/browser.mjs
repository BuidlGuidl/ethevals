import fs from 'node:fs/promises';
import path from 'node:path';
import net from 'node:net';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { chromium, privateKeyToAccount, generatePrivateKey, encodeFunctionData, formatUnits } from './deps.mjs';
import { rpc, balance, fund, reserve, send, POOL, USDC, USDT, AUSDC, AUSDT, pool, erc20 } from './chain.mjs';
import { injectWallet, requestedSupplies } from './wallet.mjs';
import { connect, prepareAction, submitAction, dismiss, visibleValues, CouldNotDrive } from './controls.mjs';

export const CHECKS = ['deposit_usdc', 'shows_deposit', 'shows_apy', 'withdraw_partial', 'withdraw_all',
  'deposit_usdt_leftover_allowance', 'refuses_over_cap', 'atomic_deposit'];
const here = path.dirname(fileURLToPath(import.meta.url));
const workspace = path.resolve(process.argv[2] || '/workspace');
const output = path.resolve(process.argv[3] || '/logs/verifier');
await fs.mkdir(output, { recursive: true });
const checksPath = path.join(output, 'checks.json');
let checks;
try { checks = JSON.parse(await fs.readFile(checksPath, 'utf8')); } catch { checks = {}; }
checks = Object.fromEntries(Object.entries(checks).filter(([name]) => name === 'compile'));
for (const check of CHECKS) checks[check] = { passed: false, reason: 'Browser journey did not complete.' };
await fs.writeFile(path.join(output, 'cap-page.txt'), 'could not drive: the cap journey did not complete\n');
const stringify = data => JSON.stringify(data, (_, value) => typeof value === 'bigint' ? value.toString() : value, 2);
const saveJson = (name, data) => fs.writeFile(path.join(output, name), stringify(data) + '\n');
const record = async (name, passed, reason) => {
  checks[name] = { passed: Boolean(passed), reason: reason.replace(/\s+/g, ' ').slice(0, 1200) };
  await saveJson('checks.json', checks);
};
if (checks.compile?.passed === false) {
  for (const check of CHECKS) await record(check, false, 'The project did not compile. See build.log and typecheck.log.');
  process.exit(0);
}
const processes = [];
let browser;
let active;
const started = Date.now();

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
async function until(fn, timeout = 20_000) {
  const deadline = Date.now() + timeout;
  let lastError;
  do {
    try { const result = await fn(); if (result) return result; } catch (error) { lastError = error; }
    await new Promise(resolve => setTimeout(resolve, 200));
  } while (Date.now() < deadline);
  if (lastError) throw lastError;
  return false;
}
async function capture(session, name) {
  await until(() => session.wallet.pending === 0, 5000);
  await fs.writeFile(path.join(output, `${name}-page.txt`), await session.page.locator('body').innerText());
  await session.page.screenshot({ path: path.join(output, `${name}.png`), fullPage: true });
  await saveJson(`${name}-wallet.json`, { requests: session.wallet.requests, transactions: session.wallet.transactions });
}

try {
  const source = process.argv[4] || JSON.parse(await fs.readFile(path.join(workspace, 'chain_context.json'), 'utf8')).rpcUrl;
  const forkPort = await port();
  const serverPort = await port();
  const mainRpc = `http://127.0.0.1:${forkPort}`;
  const block = await rpc(source, 'eth_blockNumber');
  start('anvil', ['--host', '127.0.0.1', '--port', String(forkPort), '--accounts', '0', '--chain-id', '1', '--base-fee', '0', '--silent', '--fork-url', source, '--fork-block-number', String(Number(block))], workspace, 'fork.log');
  await until(async () => await rpc(mainRpc, 'eth_chainId') === '0x1', 30_000);
  await rpc(mainRpc, 'anvil_setBlockTimestampInterval', [0]);
  const account = privateKeyToAccount(generatePrivateKey());
  await fund(mainRpc, account);
  const initial = await reserve(mainRpc);
  if (initial.room < 100_000_000n || initial.room > 9_000_000_000n) throw new Error('Fork supply-cap room is outside the fixture bounds');
  await saveJson('fixture.json', { address: account.address, sourceBlock: block, ...initial });
  let snapshot = await rpc(mainRpc, 'evm_snapshot');
  async function reset() {
    if (active) { await active.context.close(); active = null; }
    if (!await rpc(mainRpc, 'evm_revert', [snapshot])) throw new Error('Fork snapshot restore failed');
    snapshot = await rpc(mainRpc, 'evm_snapshot');
  }
  start('pnpm', ['exec', 'vite', 'preview', '--host', '127.0.0.1', '--port', String(serverPort), '--strictPort'], workspace, 'preview.log');
  const origin = `http://127.0.0.1:${serverPort}`;
  await until(async () => (await fetch(origin)).ok, 30_000);
  browser = await chromium.launch({ headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage'] });
  async function session({ atomic = false } = {}) {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1100 }, serviceWorkers: 'block' });
    // Fulfill every browser JSON-RPC request, including /rpc proxies and chain:8545.
    await context.route('**/*', async route => {
      const request = route.request();
      const headers = { 'access-control-allow-origin': '*', 'access-control-allow-headers': '*', 'access-control-allow-methods': 'POST, OPTIONS', 'access-control-allow-private-network': 'true' };
      if (request.method() === 'OPTIONS') return route.fulfill({ status: 204, headers });
      let payload;
      try { payload = request.postDataJSON(); } catch { return route.continue(); }
      if (!payload || !(Array.isArray(payload) ? payload.every(item => typeof item.method === 'string') : typeof payload.method === 'string')) return route.continue();
      const dispatch = async item => {
        try {
          // Page reads see the fork. Writes and chain controls belong to the wallet only.
          if (/^(anvil_|evm_|wallet_|eth_send|eth_sign)/.test(item.method)) throw new Error('Page RPC permits reads only');
          return { jsonrpc: '2.0', id: item.id, result: await rpc(mainRpc, item.method, item.params || []) };
        } catch (error) { return { jsonrpc: '2.0', id: item.id, error: { code: error.code || -32603, message: error.message, data: error.data } }; }
      };
      const result = Array.isArray(payload) ? await Promise.all(payload.map(dispatch)) : await dispatch(payload);
      await route.fulfill({ status: 200, contentType: 'application/json', headers, body: stringify(result) });
    });
    const wallet = await injectWallet(context, { account, mainRpc, atomic });
    const page = await context.newPage();
    page.setDefaultTimeout(5000);
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    active = { page, context, wallet, errors };
    await page.goto(origin, { waitUntil: 'domcontentloaded' });
    await connect(page, account.address);
    await until(async () => (await visibleValues(page, 'USDC')).percentages.length > 0, 15_000);
    return active;
  }
  async function seedUSDC() {
    await send(mainRpc, account, { to: USDC, data: encodeFunctionData({ abi: erc20, functionName: 'approve', args: [POOL, 100_000_000n] }) });
    const result = await send(mainRpc, account, { to: POOL, data: encodeFunctionData({ abi: pool, functionName: 'supply', args: [USDC, 100_000_000n, account.address, 0] }) });
    if (result.receipt.status !== '0x1') throw new Error('Withdrawal fixture supply failed');
  }
  async function journey(names, fn) {
    try { await fn(); }
    catch (error) {
      const reason = error instanceof CouldNotDrive ? error.message : `Journey failed: ${error.shortMessage || error.message}`;
      for (const name of names) if (checks[name].reason === 'Browser journey did not complete.') await record(name, false, reason);
      await saveJson(`${names[0]}-error.json`, { error: error.stack, pageErrors: active?.errors });
      if (active) await capture(active, `${names[0]}-failure`).catch(() => {});
      if (active && names.includes('refuses_over_cap')) {
        await fs.writeFile(path.join(output, 'cap-page.txt'), `${reason}\n\n${await active.page.locator('body').innerText()}`);
        await active.page.screenshot({ path: path.join(output, 'cap-page.png'), fullPage: true }).catch(() => {});
      }
    }
  }
  await journey(['deposit_usdc', 'shows_deposit', 'shows_apy'], async () => {
    const s = await session();
    const action = await prepareAction(s.page, 'USDC', 'deposit', '100');
    await submitAction(action);
    const success = await until(async () => Math.abs(Number(await balance(mainRpc, AUSDC, account.address)) - 100_000_000) <= 10_000);
    const deposited = await balance(mainRpc, AUSDC, account.address);
    await record('deposit_usdc', success, `100 USDC deposit left ${formatUnits(deposited, 6)} aUSDC.`);
    await dismiss(s.page);
    let values;
    const display = success && await until(async () => {
      values = await visibleValues(s.page, 'USDC');
      return values.numbers.some(value => Math.abs(value - Number(deposited) / 1e6) <= 0.01);
    });
    await record('shows_deposit', display, `aUSDC balance ${formatUnits(deposited, 6)}; visible deposit values ${JSON.stringify(values?.numbers || [])}.`);
    values = await visibleValues(s.page, 'USDC');
    const market = await reserve(mainRpc);
    await record('shows_apy', values.percentages.some(value => Math.abs(value - market.apy) <= 0.01), `Compounded APY ${market.apy.toFixed(6)}%; visible USDC percentages ${JSON.stringify(values.percentages)}.`);
    await capture(s, 'deposit-usdc');
  });
  // Partial and Max withdrawals have their own funded position even when deposit failed.
  await journey(['withdraw_partial', 'withdraw_all'], async () => {
    if (!checks.deposit_usdc.passed) { await reset(); await seedUSDC(); await session(); }
    const s = active;
    await dismiss(s.page);
    await submitAction(await prepareAction(s.page, 'USDC', 'withdraw', '40'));
    const partial = await until(async () => Math.abs(Number(await balance(mainRpc, AUSDC, account.address)) - 60_000_000) <= 10_000);
    await record('withdraw_partial', partial, `40 USDC withdrawal left ${formatUnits(await balance(mainRpc, AUSDC, account.address), 6)} aUSDC.`);
    await capture(s, 'withdraw-partial');
    await dismiss(s.page);
    await submitAction(await prepareAction(s.page, 'USDC', 'withdraw', '', true));
    const closed = await until(async () => await balance(mainRpc, AUSDC, account.address) === 0n);
    await record('withdraw_all', closed, `The page's withdraw-all control left ${formatUnits(await balance(mainRpc, AUSDC, account.address), 6)} aUSDC.`);
    await capture(s, 'withdraw-all');
  });
  await reset();
  await journey(['deposit_usdt_leftover_allowance'], async () => {
    await send(mainRpc, account, { to: USDT, data: encodeFunctionData({ abi: erc20, functionName: 'approve', args: [POOL, 1_000_000n] }) });
    const allowance = BigInt(await rpc(mainRpc, 'eth_call', [{ to: USDT, data: encodeFunctionData({ abi: erc20, functionName: 'allowance', args: [account.address, POOL] }) }, 'latest']));
    if (allowance !== 1_000_000n) throw new Error('Leftover allowance fixture failed');
    const s = await session();
    await submitAction(await prepareAction(s.page, 'USDT', 'deposit', '100'));
    const success = await until(async () => Math.abs(Number(await balance(mainRpc, AUSDT, account.address)) - 100_000_000) <= 10_000);
    await record('deposit_usdt_leftover_allowance', success, `Initial Pool allowance 1 USDT; deposit left ${formatUnits(await balance(mainRpc, AUSDT, account.address), 6)} aUSDT.`);
    await capture(s, 'deposit-usdt');
  });
  await reset();
  await journey(['refuses_over_cap'], async () => {
    const market = await reserve(mainRpc);
    // Exceed even cap minus totalSupply, a conservative upper bound on actual room.
    const oversized = market.cap - market.total + 1_000_000_000n;
    const s = await session();
    const action = await prepareAction(s.page, 'USDC', 'deposit', formatUnits(oversized, 6));
    const before = s.wallet.requests.length;
    await submitAction(action);
    await s.page.waitForTimeout(5000);
    const supplies = requestedSupplies(s.wallet.requests.slice(before));
    const doomed = supplies.filter(call => call.args[0].toLowerCase() === USDC.toLowerCase() && call.args[1] > market.room);
    await record('refuses_over_cap', doomed.length === 0, `Asked for ${formatUnits(oversized, 6)} USDC with ${formatUnits(market.room, 6)} room; doomed wallet supply requests ${doomed.length}.`);
    await capture(s, 'cap');
    await fs.copyFile(path.join(output, 'cap.png'), path.join(output, 'cap-page.png'));
    await saveJson('cap-room.json', { ...market, oversized, supplies });
  });
  await reset();
  await journey(['atomic_deposit'], async () => {
    const bytecode = (await fs.readFile(path.join(here, 'wallet-bytecode.txt'), 'utf8')).trim();
    const implementation = '0x0000000000000000000000000000000000007702';
    await rpc(mainRpc, 'anvil_setCode', [implementation, bytecode]);
    await rpc(mainRpc, 'anvil_setCode', [account.address, `0xef0100${implementation.slice(2)}`]);
    const s = await session({ atomic: true });
    const action = await prepareAction(s.page, 'USDC', 'deposit', '100');
    const before = s.wallet.requests.length;
    await submitAction(action);
    const deposited = await until(async () => Math.abs(Number(await balance(mainRpc, AUSDC, account.address)) - 100_000_000) <= 10_000);
    const requests = s.wallet.requests.slice(before);
    await until(() => s.wallet.pending === 0, 5000);
    const transactions = s.wallet.transactions;
    const bundles = requests.filter(request => request.method === 'wallet_sendCalls');
    const signedPermit = requests.some(request => /^eth_signTypedData/.test(request.method));
    const permitSupply = requestedSupplies(requests).some(call => call.functionName === 'supplyWithPermit');
    const acceptedMethod = bundles.length === 1 || signedPermit && permitSupply;
    await record('atomic_deposit', deposited && transactions.length === 1 && acceptedMethod && transactions[0].receipt.status === '0x1',
      `Atomic-capable wallet: deposited ${Boolean(deposited)}; onchain transactions ${transactions.length}; bundles ${bundles.length}; permit signature ${signedPermit}; supplyWithPermit ${permitSupply}.`);
    await capture(s, 'atomic');
  });
} catch (error) {
  await saveJson('browser-error.json', { error: error.stack });
  for (const check of CHECKS) if (checks[check].reason === 'Browser journey did not complete.') await record(check, false, `Browser setup failed: ${error.message}`);
} finally {
  if (browser) await browser.close().catch(() => {});
  for (const { child, log, logfile } of processes.reverse()) {
    try { process.kill(-child.pid, 'SIGTERM'); } catch { /* Already exited. */ }
    await fs.writeFile(path.join(output, logfile), Buffer.concat(log));
  }
  await saveJson('checks.json', checks);
  await saveJson('timing.json', { browserSeconds: (Date.now() - started) / 1000 });
}
