import fs from 'node:fs/promises';
import path from 'node:path';
import { createHarness, until } from './harness.mjs';
import { connect, prepareSwap, pressThrough, nextAction } from './controls.mjs';
import { chainReader, funding, classify, classifyRequest, hasSwapLog, TOKENS } from './chain.mjs';
import { createMarket } from './market.mjs';
import { belief, deltas, feeCheck, finiteDeadline, allowancesEmpty, routersEmpty, minimumCheck, receivedCheck } from './checks.mjs';
import { walletIdle } from './rpc-policy.mjs';
import { rpc } from './rpc.mjs';

export const CHECKS = ['swaps_assets', 'cut_only_on_swap', 'honors_minimum', 'exact_approvals', 'finite_deadline', 'native_eth', 'routers_empty', 'shows_received'];
const workspace = path.resolve(process.argv[2] || '/workspace');
const output = path.resolve(process.argv[3] || '/logs/verifier');
const sourceContext = process.argv[4] || '/chain/chain_context.json';
await fs.mkdir(output, { recursive: true });
const stringify = value => JSON.stringify(value, (_, item) => typeof item === 'bigint' ? item.toString() : item, 2) + '\n';
const save = (name, value) => fs.writeFile(path.join(output, name), stringify(value));
let previous = {};
try { previous = JSON.parse(await fs.readFile(path.join(output, 'checks.json'), 'utf8')); } catch { /* Local runs can omit compile records. */ }
const checks = Object.fromEntries(Object.entries(previous).filter(([name]) => name === 'compile'));
for (const name of CHECKS) checks[name] = { passed: false, reason: 'Browser journeys did not complete.' };
await fs.writeFile(path.join(output, 'price-change.txt'), 'could not drive: market journey did not complete\n');
await save('moved-wallet.json', { requests: [], transactions: [] });
await save('checks.json', checks);
if (checks.compile?.passed === false) process.exit(0);
const outcomes = [];
let harness;
const start = Date.now();
try {
  const context = JSON.parse(await fs.readFile(sourceContext, 'utf8'));
  const treasury = context.treasury;
  if (!/^0x[0-9a-fA-F]{40}$/.test(treasury)) throw new Error('Trusted chain context has no treasury');
  harness = await createHarness({ workspace, output, sourceContext, funding });
  if (await rpc(harness.mainRpc, 'eth_getCode', [treasury, 'latest']) !== '0x') throw new Error('Treasury fixture has code');
  const reader = chainReader(harness.mainRpc, harness.account.address, treasury);
  const market = createMarket({ url: harness.mainRpc, output });
  const baseline = await reader.state();
  await save('fixture.json', { sourceBlock: harness.sourceBlock, ...baseline });

  async function runSwap({ name, input, output: tokenOut, amount, mode = 'normal', seed }) {
    await harness.reset();
    if (seed) await reader.seedUSDT(harness.account, seed);
    const before = await reader.state();
    let session;
    let hookError;
    const swapRequests = [];
    let marketResult;
    let lastDisplay;
    const pressRecords = [];
    const result = { name, input, output: tokenOut, mode, completed: false, success: false, flags: {} };
    const isSwapRequest = request => {
      if (['eth_sendTransaction', 'wallet_sendTransaction'].includes(request.method)) return classify(request.params[0], treasury).kind === 'swap';
      return request.method === 'wallet_sendCalls' && request.params[0].calls.some(tx => classify(tx, treasury).kind === 'swap');
    };
    const snapshot = async press => {
      pressRecords.push(press);
      lastDisplay = press.belief;
      await fs.writeFile(path.join(output, `${name}-press-${pressRecords.length}.txt`), press.text);
      await save(`${name}-presses.json`, pressRecords);
    };
    try {
      session = await harness.session({ beforeSend: async (tx, entry) => {
        const classification = classify(tx, treasury);
        entry.classification = classification;
        if (classification.kind !== 'swap') return;
        swapRequests.push(entry);
        // The page can update during an approval. Save its last visible belief at the actual swap request too.
        const text = await session.page.locator('body').innerText();
        lastDisplay = belief(text, tokenOut);
        await snapshot({ time: Date.now(), label: 'wallet swap request', text, belief: lastDisplay });
        if (mode === 'reject') throw Object.assign(new Error('User rejected the swap request'), { code: 4001 });
        if (mode === 'race' && !marketResult) {
          try { marketResult = await market.moveMarket(2, 'eth-buyers'); }
          catch (error) { hookError = error; throw error; }
          await save(`${name}-market.json`, marketResult);
        }
      } });
      await connect(session.page, harness.account.address);
      const action = await prepareSwap(session.page, input, tokenOut, amount);
      if (mode === 'moved') {
        const initialButton = await nextAction(session.page);
        // Open a review when the page offers one, so the move happens between quote and confirmation.
        if (initialButton && /^review\b/i.test(await initialButton.innerText())) {
          const text = await session.page.locator('body').innerText();
          await snapshot({ time: Date.now(), label: await initialButton.innerText(), text, belief: belief(text, tokenOut) });
          await initialButton.click();
          await walletIdle(session.wallet);
        }
        const beforeMove = await session.page.locator('body').innerText();
        await fs.writeFile(path.join(output, 'moved-before.txt'), beforeMove);
        const quotedAt = Date.now();
        marketResult = await market.moveMarket(2, 'eth-buyers');
        await save('moved-market.json', marketResult);
        // Keep the saved page's documented 30-second quote expiry observable even when the smaller mover finishes sooner.
        const remaining = Math.max(0, 32_000 - (Date.now() - quotedAt));
        if (remaining) await session.page.waitForTimeout(remaining);
      }
      await pressThrough(action, { wallet: session.wallet, isSwapRequest, snapshot,
        maxPresses: mode === 'moved' && pressRecords.length ? 5 : 6 });
      if (hookError) throw hookError;
      if (!swapRequests.length) throw new Error('could not drive: no classified swap request after six presses or no enabled action');
      await until(async () => /(?:received|reverted|rejected|failed|cancel)/i.test(await session.page.locator('body').innerText()), 12_000);
      await session.page.waitForTimeout(500);
      result.completed = true;
    } catch (error) {
      if (hookError || error.infrastructure) throw hookError || error;
      result.error = error.message;
      await save(`${name}-error.json`, { error: error.stack, pageErrors: session?.errors });
    }
    const transactions = session ? await reader.transactions(session.wallet) : [];
    if (session) for (const request of session.wallet.requests) request.classification ||= classifyRequest(request, treasury);
    const after = await reader.state();
    const delta = deltas(before, after, transactions);
    const swaps = transactions.filter(tx => tx.relevant);
    const successful = swaps.filter(tx => tx.receipt.status === '0x1' && hasSwapLog(tx.receipt));
    result.success = successful.length > 0 && delta.user[tokenOut] > 0n && delta.user[input] < 0n;
    const pageText = session ? await session.page.locator('body').innerText() : '';
    result.delta = delta;
    result.flags.fee = result.completed && feeCheck(delta, input, tokenOut, result.success);
    if (mode === 'reject') result.flags.fee &&= swapRequests.some(entry => entry.error?.includes('rejected')) && !result.success;
    if (mode === 'race') result.flags.fee &&= Boolean(marketResult && swaps.length);
    result.flags.minimum = result.success && successful.every(tx => minimumCheck(lastDisplay || {}, tx.decoded, tokenOut, delta.user[tokenOut]).passed);
    result.flags.approvals = result.success && allowancesEmpty(after);
    result.leftoverAllowances = {
      erc20: after.erc20Allowances.filter(item => item.amount !== 0n),
      permit2: after.permit2Allowances.filter(item => item.amount !== 0n && BigInt(item.expiration) > after.timestamp),
    };
    result.flags.deadline = swaps.length > 0 && swaps.every(tx => finiteDeadline(tx.decoded));
    result.flags.native = result.success && (tokenOut !== 'ETH' || (delta.user.ETH > 0n && delta.user.WETH === 0n));
    result.flags.routers = result.success && routersEmpty(baseline, after);
    result.flags.received = result.success && receivedCheck(pageText, tokenOut, delta.user[tokenOut]).passed;
    result.minimum = successful.map(tx => minimumCheck(lastDisplay || {}, tx.decoded, tokenOut, delta.user[tokenOut]));
    result.received = receivedCheck(pageText, tokenOut, delta.user[tokenOut]);
    result.swapRequests = swapRequests.length;
    await save(`${name}-before.json`, before);
    await save(`${name}-after.json`, after);
    await save(`${name}-transactions.json`, transactions);
    await save(`${name}-result.json`, result);
    if (session) await harness.capture(session, name);
    if (mode === 'moved') {
      const initial = await fs.readFile(path.join(output, 'moved-before.txt'), 'utf8').catch(() => 'could not drive');
      await fs.writeFile(path.join(output, 'price-change.txt'), `Before the market move:\n${initial}\n\nAfter the move, at each press and wallet request:\n${pressRecords.map(press => `${press.time} ${press.label}\n${press.text}`).join('\n\n')}\n\nFinal page:\n${pageText}\n${result.error || ''}\n`);
    }
    outcomes.push(result);
    console.log(stringify({ event: 'journey', name, success: result.success, flags: result.flags, error: result.error }));
    return { result, transactions };
  }
  await runSwap({ name: 'usdc-eth', input: 'USDC', output: 'ETH', amount: '500' });
  await runSwap({ name: 'eth-usdc', input: 'ETH', output: 'USDC', amount: '1' });
  // Discover this page's actual spender, then replay from a clean snapshot with that one seeded allowance.
  const probe = await runSwap({ name: 'usdt-probe', input: 'USDT', output: 'ETH', amount: '1000' });
  const approval = probe.transactions.find(tx => tx.tx.to?.toLowerCase() === TOKENS.USDT.toLowerCase() && tx.decoded.function === 'approve');
  const spender = approval?.decoded.spender || approval?.decoded.arg0;
  if (probe.result.success && !spender) throw new Error('USDT probe has no approval spender');
  await runSwap({ name: 'usdt-eth', input: 'USDT', output: 'ETH', amount: '1000', seed: spender });
  await runSwap({ name: 'moved', input: 'USDC', output: 'ETH', amount: '2000', mode: 'moved' });
  await runSwap({ name: 'rejected', input: 'USDC', output: 'ETH', amount: '500', mode: 'reject' });
  await runSwap({ name: 'reverted', input: 'USDC', output: 'ETH', amount: '500', mode: 'race' });
  const normal = outcomes.filter(result => ['usdc-eth', 'eth-usdc', 'usdt-eth', 'moved'].includes(result.name));
  const flag = { swaps_assets: null, cut_only_on_swap: 'fee', honors_minimum: 'minimum', exact_approvals: 'approvals', finite_deadline: 'deadline', native_eth: 'native', routers_empty: 'routers', shows_received: 'received' };
  for (const name of CHECKS) {
    const selected = name === 'cut_only_on_swap' ? outcomes.filter(result => result.name !== 'usdt-probe')
      : name === 'finite_deadline' ? outcomes.filter(result => result.name !== 'usdt-probe' && result.name !== 'rejected') : normal;
    const passed = selected.every(result => name === 'swaps_assets' ? result.success : result.flags[flag[name]]);
    const reasons = selected.map(result => {
      const status = result.error || (name === 'swaps_assets' ? result.success : result.flags[flag[name]]);
      let detail = '';
      if (name === 'honors_minimum') detail = result.minimum.map(item => item.reason).join('; ') || 'could not read a minimum';
      if (name === 'shows_received') detail = result.received.reason;
      if (name === 'cut_only_on_swap') detail = `swap ${result.success ? 'succeeded' : 'did not happen'}; user deltas ${stringify(result.delta.user).trim()}; treasury deltas ${stringify(result.delta.treasury).trim()} in base units`;
      if (name === 'exact_approvals' && !result.flags.approvals) detail = `Remaining allowances: ${stringify(result.leftoverAllowances).trim()}`;
      if (name === 'finite_deadline' && !result.flags.deadline) detail = 'A router or Swap-log transaction has no finite decoded deadline.';
      return `${result.name}: ${status}${detail ? `; ${detail}` : ''}`;
    });
    checks[name] = { passed, reason: reasons.join('; ').replace(/\s+/g, ' ').slice(0, 4000) };
  }
  await save('journeys.json', outcomes);
} catch (error) {
  await save('browser-error.json', { error: error.stack });
  if (error.pageFailure) {
    for (const name of CHECKS) checks[name] = { passed: false, reason: `Page setup failed: ${error.message}` };
  } else { console.error(error); process.exitCode = 1; }
} finally {
  if (harness) await harness.close();
  await save('checks.json', checks);
  await save('timing.json', { browserSeconds: (Date.now() - start) / 1000 });
}
