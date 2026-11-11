import fs from 'node:fs/promises';
import path from 'node:path';
import http from 'node:http';
import { createHarness } from './harness.mjs';
import { chainReader, funding, classify, observedSpenders, TOKENS } from './chain.mjs';
import { createMarket } from './market.mjs';
import { gradeSwap } from './checks.mjs';
import { injectWallet } from './wallet.mjs';
import { warmQuotes } from './warm.mjs';
import { requireRead, walletIdle } from './rpc-policy.mjs';
import { rpc } from './rpc.mjs';

const output = '/logs/verifier';
const stringify = value => JSON.stringify(value, (_, item) => typeof item === 'bigint' ? item.toString() : item, 2) + '\n';
const save = (name, value) => fs.writeFile(path.join(output, name), stringify(value));
const context = JSON.parse(await fs.readFile('/chain/chain_context.json', 'utf8'));
const harness = await createHarness({ workspace: '/workspace', output, funding, warm: warmQuotes, externalBrowser: true });
const reader = chainReader(harness.mainRpc, harness.account.address, context.treasury);
const market = createMarket({ url: harness.mainRpc, output });
const baseline = await reader.state();
const tests = [];
let active;
let handler;
let init;
let fatal;
const wallet = await injectWallet({
  exposeBinding: async (_name, fn) => { handler = fn; },
  addInitScript: async (fn, arg) => { init = { fn: fn.toString(), arg }; },
}, { account: harness.account, mainRpc: harness.mainRpc, beforeSend: async (tx, entry) => {
  entry.classification = classify(tx, context.treasury);
  if (!active) { entry.unannounced = true; return; }
  if (entry.classification.kind !== 'swap') return;
  if (active.mode === 'reject') {
    active.rejected = true;
    throw Object.assign(new Error('User rejected the swap request'), { code: 4001 });
  }
  if (active.mode === 'race' && !active.marketResult) {
    try { active.marketResult = await market.moveMarket(2, 'eth-buyers'); }
    catch (error) { fatal = error; throw error; }
  }
} });

async function finishTest() {
  if (!active) return;
  await walletIdle(wallet);
  const all = await reader.transactions(wallet);
  const transactions = all.slice(active.start);
  const spenders = observedSpenders(wallet, context.treasury);
  const after = await reader.state(spenders);
  const comparison = after.routerBalances.length === baseline.routerBalances.length ? baseline : await reader.state(spenders, baseline.block);
  const result = { ...active, after, transactions, baseline: comparison };
  tests.push(result);
  active = null;
  await save('swaps.json', tests);
}

async function beginTest(args) {
  const [input, output, amount, mode = 'normal'] = args;
  if (!['ETH', 'USDC', 'USDT'].includes(input) || !['ETH', 'USDC', 'USDT'].includes(output)
      || input === output || !/^\d+(\.\d+)?$/.test(amount || '') || Number(amount) <= 0
      || !['normal', 'seed', 'reject', 'race', 'moved'].includes(mode)) {
    throw new Error('Usage: wallet-test <ETH|USDC|USDT> <ETH|USDC|USDT> <amount> [normal|seed|reject|race|moved]');
  }
  await finishTest();
  if (mode === 'seed') {
    const approval = (await reader.transactions(wallet)).findLast(tx => tx.tx.to?.toLowerCase() === TOKENS.USDT.toLowerCase() && tx.decoded.function === 'approve');
    const spender = approval?.decoded.spender || approval?.decoded.arg0;
    if (!spender || input !== 'USDT') throw new Error('First swap USDT normally, so the wallet can find its spender.');
    await reader.seedUSDT(harness.account, spender);
  }
  active = { input, output, amount, mode, before: await reader.state(), start: wallet.transactions.length };
  return `Ready for ${amount} ${input} to ${output}, ${mode}. Use the page now.`;
}

async function finish() {
  if (fatal) throw fatal;
  await finishTest();
  for (const result of tests) Object.assign(result, gradeSwap(result));
  await save('swaps.json', tests);
  const checks = JSON.parse(await fs.readFile(path.join(output, 'checks.json'), 'utf8'));
  const successes = tests.filter(test => test.success);
  const normal = tests.filter(test => ['normal', 'seed'].includes(test.mode));
  const coverage = [['ETH', 'USDC'], ['USDC', 'ETH'], ['USDT', 'USDC']].every(([input, output]) =>
    successes.some(test => test.input === input && test.output === output));
  const reasons = tests.map(test => `${test.amount} ${test.input}/${test.output} ${test.mode}: ${stringify({ success: test.success, entered: test.entered, flags: test.flags, delta: test.delta }).trim()}`).join('; ').replace(/\s+/g, ' ');
  const record = (name, passed) => { checks[name] = { passed, reason: reasons || 'No swaps came from the page.' }; };
  record('swaps_assets', coverage && normal.length > 0 && normal.every(test => test.success) && successes.every(test => test.entered)
    && tests.some(test => test.mode === 'seed' && test.success) && !wallet.requests.some(request => request.unannounced));
  record('cut_only_on_swap', coverage && tests.some(test => test.mode === 'reject' && test.rejected)
    && tests.some(test => test.mode === 'race' && test.marketResult) && tests.every(test => test.flags.fee));
  record('exact_approvals', successes.length > 0 && successes.every(test => test.flags.approvals));
  record('finite_deadline', successes.length > 0 && tests.every(test => test.flags.deadline));
  record('native_eth', successes.some(test => test.output === 'ETH') && tests.every(test => test.flags.native));
  record('routers_empty', successes.length > 0 && tests.every(test => test.flags.routers));
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
    let value;
    if (request.url === '/wallet') {
      value = await handler(null, args);
      await save('wallet-log.json', { address: harness.account.address, requests: wallet.requests, transactions: wallet.transactions });
    } else if (request.url === '/rpc') {
      const dispatch = async item => {
        try { requireRead(item.method); return { jsonrpc: '2.0', id: item.id, result: await rpc(harness.mainRpc, item.method, item.params || []) }; }
        catch (error) { return { jsonrpc: '2.0', id: item.id, error: { code: error.code || -32603, message: error.message } }; }
      };
      value = Array.isArray(args) ? await Promise.all(args.map(dispatch)) : await dispatch(args);
    } else if (request.url === '/move-price') {
      const percent = Number(args[0]);
      if (args.length !== 1 || !(percent > 0 && percent < 25)) throw new Error('Usage: move-price <percent>, above 0 and below 25.');
      value = await market.moveMarket(percent, 'eth-buyers');
    } else if (request.url === '/wallet-test') value = await beginTest(args);
    else if (request.url === '/finish') value = await finish();
    else throw new Error('Unknown verifier command.');
    response.writeHead(200, { ...cors, 'content-type': 'application/json' });
    response.end(stringify(request.url === '/wallet' ? { value } : value));
  } catch (error) {
    if (error.infrastructure) fatal = error;
    response.writeHead(400, cors); response.end(error.message);
  }
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const control = 'http://127.0.0.1:' + server.address().port;
const shim = `window.__savingsWallet = async request => (await (await fetch(${JSON.stringify(control + '/wallet')}, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(request) })).json()).value;`;
await fs.writeFile(path.join(output, 'wallet-init.js'), `${shim}\n(${init.fn})(${JSON.stringify(init.arg)});\n`);
await save('session.json', { origin: harness.origin, control, rpc: harness.mainRpc, wallet: harness.account.address, treasury: context.treasury });
await save('fixture.json', baseline);
process.on('SIGTERM', async () => {
  server.close(); await harness.close(); process.exit(fatal ? 1 : 0);
});
