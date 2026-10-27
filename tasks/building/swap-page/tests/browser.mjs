import fs from 'node:fs/promises';
import path from 'node:path';
import { createHarness, until } from './harness.mjs';
import { connect, prepareSwap, pressThrough, nextAction, waitForQuote, openDetails } from './controls.mjs';
import { chainReader, funding, classify, classifyRequest, observedSpenders, TOKENS } from './chain.mjs';
import { createMarket } from './market.mjs';
import { belief, confirmedBelief, gradeJourney, scoredJourneys } from './checks.mjs';
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
    let moveStarted;
    let moveEnded;
    const result = { name, input, output: tokenOut, amount, mode, completed: false, success: false, flags: {} };
    const isSwapRequest = request => {
      const classification = classifyRequest(request, treasury);
      return classification.kind === 'swap' || classification.calls?.some(call => call.kind === 'swap');
    };
    const snapshot = async press => {
      pressRecords.push(press);
      if (press.label !== 'wallet swap request') lastDisplay = confirmedBelief(lastDisplay, press.belief);
      await fs.writeFile(path.join(output, `${name}-press-${pressRecords.length}.txt`), press.text);
      await save(`${name}-presses.json`, pressRecords);
    };
    try {
      session = await harness.session({ beforeSend: async (tx, entry) => {
        const classification = classify(tx, treasury);
        entry.classification = classification;
        if (classification.kind !== 'swap') return;
        swapRequests.push(entry);
        // Wallet-pending views are evidence, not a new user confirmation.
        const text = await session.page.locator('body').innerText();
        await snapshot({ time: Date.now(), label: 'wallet swap request', text, belief: belief(text, tokenOut) });
        if (mode === 'reject') throw Object.assign(new Error('User rejected the swap request'), { code: 4001 });
        if (['race', 'drift'].includes(mode) && !marketResult) {
          try { marketResult = await market.moveMarket(mode === 'drift' ? 0.3 : 2, 'eth-buyers'); }
          catch (error) { hookError = error; throw error; }
          await save(`${name}-market.json`, marketResult);
        }
      } });
      await connect(session.page, harness.account.address);
      const action = await prepareSwap(session.page, input, tokenOut, amount);
      if (mode === 'moved') {
        await waitForQuote(session.page, tokenOut);
        await session.page.evaluate(() => {
          window.swapTextEvidence = [];
          const capture = () => {
            const text = document.body.innerText;
            if (window.swapTextEvidence.at(-1)?.text !== text) window.swapTextEvidence.push({ time: Date.now(), text });
          };
          new MutationObserver(capture).observe(document.body, { subtree: true, childList: true, characterData: true, attributes: true });
          capture();
        });
        const initialButton = await nextAction(session.page);
        // Open a review when the page offers one, so the move happens between quote and confirmation.
        if (initialButton && /^review\b/i.test(await initialButton.innerText())) {
          await openDetails(action);
          const text = await session.page.locator('body').innerText();
          await snapshot({ time: Date.now(), label: await initialButton.innerText(), text, belief: belief(text, tokenOut) });
          await initialButton.click();
          await walletIdle(session.wallet);
        }
        await openDetails(action);
        const beforeMove = await session.page.locator('body').innerText();
        await fs.writeFile(path.join(output, 'moved-before.txt'), beforeMove);
        moveStarted = Date.now();
        marketResult = await market.moveMarket(2, 'eth-buyers');
        moveEnded = Date.now();
        await save('moved-market.json', marketResult);
        // Every page gets the same one-minute observation interval after the move.
        await session.page.waitForTimeout(60_000);
      }
      await pressThrough(action, { wallet: session.wallet, isSwapRequest, snapshot,
        maxPresses: mode === 'moved' && pressRecords.length ? 5 : 6 });
      if (hookError) throw hookError;
      if (!swapRequests.length) throw new Error('could not drive: no classified swap request after six presses or no enabled action');
      const requestText = pressRecords.findLast(press => press.label === 'wallet swap request')?.text;
      await until(async () => (await session.page.locator('body').innerText()) !== requestText, 12_000);
      await walletIdle(session.wallet);
      await session.page.waitForTimeout(500);
      result.completed = true;
    } catch (error) {
      if (hookError || error.infrastructure) throw hookError || error;
      result.error = error.message;
      await save(`${name}-error.json`, { error: error.stack, pageErrors: session?.errors });
    }
    const transactions = session ? await reader.transactions(session.wallet) : [];
    if (session) for (const request of session.wallet.requests) request.classification ||= classifyRequest(request, treasury);
    const spenders = session ? observedSpenders(session.wallet, treasury) : [];
    const after = await reader.state(spenders);
    const journeyBaseline = after.routerBalances.length === baseline.routerBalances.length ? baseline : await reader.state(spenders, baseline.block);
    await save(`${name}-baseline.json`, journeyBaseline);
    const pageText = session ? await session.page.locator('body').innerText() : '';
    Object.assign(result, gradeJourney({ input, output: tokenOut, amount, mode, completed: result.completed,
      before, after, baseline: journeyBaseline, transactions, display: lastDisplay, pageText, marketResult,
      rejected: swapRequests.some(entry => entry.error?.includes('rejected')) }));
    result.confirmedDisplay = lastDisplay;
    result.swapRequests = swapRequests.length;
    await save(`${name}-before.json`, before);
    await save(`${name}-after.json`, after);
    await save(`${name}-transactions.json`, transactions);
    await save(`${name}-result.json`, result);
    if (session) await harness.capture(session, name);
    if (mode === 'moved') {
      const initial = await fs.readFile(path.join(output, 'moved-before.txt'), 'utf8').catch(() => 'could not drive');
      const observations = session ? await session.page.evaluate(() => window.swapTextEvidence || []) : [];
      await save('moved-text-observations.json', observations);
      const phase = time => time < moveStarted ? 'before move' : time <= moveEnded ? 'during move' : 'after move';
      const timeline = [...observations.map(item => ({ ...item, label: 'page changed' })), ...pressRecords].sort((a, b) => a.time - b.time);
      await fs.writeFile(path.join(output, 'price-change.txt'), `Before the market move:\n${initial}\n\nMove started: ${moveStarted}; ended: ${moveEnded}.\nTimeline:\n${timeline.map(press => `${press.time} (${phase(press.time)}) ${press.label}\n${press.text}`).join('\n\n')}\n\nFinal page:\n${pageText}\n${result.error || ''}\n`);
    }
    outcomes.push(result);
    console.log(stringify({ event: 'journey', name, success: result.success, flags: result.flags, error: result.error }));
    return { result, transactions };
  }
  await runSwap({ name: 'usdc-eth', input: 'USDC', output: 'ETH', amount: '500' });
  await runSwap({ name: 'eth-usdc', input: 'ETH', output: 'USDC', amount: '1' });
  // Discover this page's actual spender, then replay from a clean snapshot with that one seeded allowance.
  const probe = await runSwap({ name: 'usdt-usdc', input: 'USDT', output: 'USDC', amount: '1000' });
  const approval = probe.transactions.find(tx => tx.tx.to?.toLowerCase() === TOKENS.USDT.toLowerCase() && tx.decoded.function === 'approve');
  const spender = approval?.decoded.spender || approval?.decoded.arg0;
  if (spender) await runSwap({ name: 'usdt-seeded', input: 'USDT', output: 'USDC', amount: '1000', seed: spender });
  await runSwap({ name: 'drift', input: 'USDC', output: 'ETH', amount: '500', mode: 'drift' });
  await runSwap({ name: 'moved', input: 'USDC', output: 'ETH', amount: '2000', mode: 'moved' });
  await runSwap({ name: 'rejected', input: 'USDC', output: 'ETH', amount: '500', mode: 'reject' });
  await runSwap({ name: 'reverted', input: 'USDC', output: 'ETH', amount: '500', mode: 'race' });
  const flag = { swaps_assets: null, cut_only_on_swap: 'fee', honors_minimum: 'minimum', exact_approvals: 'approvals', finite_deadline: 'deadline', native_eth: 'native', routers_empty: 'routers', shows_received: 'received' };
  for (const name of CHECKS) {
    const selected = scoredJourneys(outcomes, name);
    const passed = selected.every(result => name === 'swaps_assets' ? result.success && result.entered : result.flags[flag[name]]);
    const reasons = selected.map(result => {
      const status = result.error || (name === 'swaps_assets' ? result.success : result.flags[flag[name]]);
      let detail = '';
      if (name === 'swaps_assets') detail = `entered ${result.amount} ${result.input}; input debit matches: ${result.entered}`;
      if (name === 'honors_minimum') detail = result.minimum.map(item => item.reason).join('; ') || 'could not read a minimum';
      if (name === 'shows_received') detail = result.received.reason;
      if (name === 'cut_only_on_swap') detail = `swap ${result.success ? 'succeeded' : 'did not happen'}; user deltas ${stringify(result.delta.user).trim()}; treasury deltas ${stringify(result.delta.treasury).trim()}; treasury in swap blocks ${stringify(result.swapTreasury).trim()} in base units`;
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
