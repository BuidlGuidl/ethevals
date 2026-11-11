import fs from 'node:fs/promises';
import path from 'node:path';
import http from 'node:http';
import { encodeFunctionData } from './deps.mjs';
import { createHarness } from './harness.mjs';
import { funding, positions, isWithdrawal, lowerSupplyCap, reserve, POOL, USDT, erc20 } from './chain.mjs';
import { gradeSavings } from './checks.mjs';
import { injectWallet } from './wallet.mjs';
import { warmSavings } from './warm.mjs';
import { pageRead, walletIdle } from './rpc-policy.mjs';
import { rpc, read, send, advanceTime } from './rpc.mjs';

// Serves the built page, the test wallet, and the judge's condition commands until /finish grades the session.
const output = '/logs/verifier';
const stringify = value => JSON.stringify(value, (_, item) => typeof item === 'bigint' ? item.toString() : item, 2) + '\n';
const save = (name, value) => fs.writeFile(path.join(output, name), stringify(value));
const harness = await createHarness({ workspace: '/workspace', output, funding, warm: warmSavings, externalBrowser: true });
const { mainRpc, account } = harness;
const conditions = [];
const typed = [];
let handler;
let init;
let fatal;
// The wallet mines each withdrawal a day after the request, so a withdrawal of a stale balance leaves interest behind.
const wallet = await injectWallet({
  exposeBinding: async (_name, fn) => { handler = fn; },
  addInitScript: async (fn, arg) => { init = { fn: fn.toString(), arg }; },
}, { account, mainRpc, beforeSend: async (tx, entry) => {
  if (!isWithdrawal(tx)) return;
  try { await advanceTime(mainRpc, 86_400); entry.minedADayLater = true; }
  catch (error) { fatal = error; throw error; }
} });

const block = async () => Number(await rpc(mainRpc, 'eth_blockNumber'));
const commands = {
  async 'move-time'([days]) {
    const value = Number(days);
    if (!(value > 0 && value <= 3650)) throw new Error('Usage: move-time <days>, above 0 and at most 3650.');
    await advanceTime(mainRpc, Math.round(value * 86_400));
    conditions.push({ kind: 'move-time', days: value, block: await block(), time: Date.now() });
    return `The chain's clock moved forward ${value} days.`;
  },
  async 'old-usdt-approval'(args) {
    if (args.length) throw new Error('Usage: old-usdt-approval');
    const approve = amount => send(mainRpc, account, { to: USDT, data: encodeFunctionData({ abi: erc20, functionName: 'approve', args: [POOL, amount] }) });
    const allowance = async () => BigInt(await read(mainRpc, USDT, erc20, 'allowance', [account.address, POOL]));
    if (await allowance() !== 0n) await approve(0n);
    await approve(1_000_000n);
    if (await allowance() !== 1_000_000n) throw Object.assign(new Error('Leftover USDT allowance setup failed'), { infrastructure: true });
    conditions.push({ kind: 'old-usdt-approval', block: await block(), time: Date.now() });
    return 'The wallet now has a 1 USDT approval to the Aave Pool.';
  },
  async 'full-cap'(args) {
    if (args.length) throw new Error('Usage: full-cap');
    const market = await lowerSupplyCap(mainRpc);
    conditions.push({ kind: 'full-cap', room: market.room, cap: market.cap, block: await block(), time: Date.now() });
    await save('cap-setup.json', market);
    return `USDC's supply cap is now ${market.cap / 1_000_000n} USDC. Aave will accept about ${Number(market.room) / 1e6} USDC more.`;
  },
  async 'wallet-network'([id]) {
    const chainId = Number(id);
    if (!Number.isSafeInteger(chainId) || chainId <= 1) throw new Error('Usage: wallet-network <chain id>, a chain other than Ethereum (1).');
    wallet.otherChain = chainId;
    wallet.chainId = chainId;
    conditions.push({ kind: 'wallet-network', chainId, time: Date.now() });
    return `The wallet is now on chain ${chainId}.`;
  },
};

async function finish() {
  if (fatal) throw fatal;
  await walletIdle(wallet);
  const end = Date.now();
  const moves = [];
  for (const transaction of wallet.transactions) {
    const mined = Number(transaction.receipt.blockNumber);
    moves.push({ hash: transaction.hash, status: transaction.receipt.status, block: mined, method: transaction.request.method,
      before: await positions(mainRpc, account.address, '0x' + (mined - 1).toString(16)),
      after: await positions(mainRpc, account.address, '0x' + mined.toString(16)) });
  }
  await save('moves.json', moves);
  await save('conditions.json', conditions);
  await save('typed.json', typed);
  const checks = JSON.parse(await fs.readFile(path.join(output, 'checks.json'), 'utf8'));
  Object.assign(checks, gradeSavings({ compile: checks.compile.passed, moves, requests: wallet.requests, conditions, typed, end }));
  for (const record of Object.values(checks)) record.reason = record.reason.replace(/\s+/g, ' ').slice(0, 1200);
  await save('checks.json', checks);
  return 'Chain checks finished.';
}

const cors = { 'access-control-allow-origin': '*', 'access-control-allow-headers': '*',
  'access-control-allow-methods': 'POST, OPTIONS', 'access-control-allow-private-network': 'true' };
const server = http.createServer(async (request, response) => {
  if (request.method === 'OPTIONS') { response.writeHead(204, cors); response.end(); return; }
  try {
    const chunks = [];
    for await (const chunk of request) chunks.push(chunk);
    const args = JSON.parse(Buffer.concat(chunks).toString() || '[]');
    const name = request.url.slice(1);
    let value;
    if (name === 'wallet') {
      value = await handler(null, args);
      await save('wallet-log.json', { address: account.address, chainId: wallet.chainId, requests: wallet.requests, transactions: wallet.transactions });
    } else if (name === 'rpc') {
      const dispatch = item => pageRead(rpc, mainRpc, item);
      value = Array.isArray(args) ? await Promise.all(args.map(dispatch)) : await dispatch(args);
    } else if (name === 'typed') {
      typed.push({ value: String(args.value ?? '').slice(0, 100), time: Date.now() });
      value = null;
    } else if (Object.hasOwn(commands, name)) {
      value = await commands[name](args);
    } else if (name === 'finish') value = await finish();
    else throw new Error('Unknown verifier command.');
    response.writeHead(200, { ...cors, 'content-type': 'application/json' });
    response.end(stringify(name === 'wallet' ? { value } : value));
  } catch (error) {
    if (error.infrastructure) fatal = error;
    response.writeHead(400, cors); response.end(error.message);
  }
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const control = 'http://127.0.0.1:' + server.address().port;
const shim = `window.__savingsWallet = async request => (await (await fetch(${JSON.stringify(control + '/wallet')}, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(request) })).json()).value;`;
// Records what is typed into the page, so the cap check knows when an amount above the room was entered.
const typing = `document.addEventListener('input', event => { const value = event.target && event.target.value; if (typeof value === 'string') fetch(${JSON.stringify(control + '/typed')}, { method: 'POST', body: JSON.stringify({ value }) }).catch(() => {}); }, true);`;
await fs.writeFile(path.join(output, 'wallet-init.js'), `${shim}\n${typing}\n(${init.fn})(${JSON.stringify(init.arg)});\n`);
await save('fixture.json', { address: account.address, sourceBlock: harness.sourceBlock, ...await reserve(mainRpc) });
await save('session.json', { origin: harness.origin, control, rpc: mainRpc, wallet: account.address });
process.on('SIGTERM', async () => {
  server.close(); await harness.close(); process.exit(fatal ? 1 : 0);
});
