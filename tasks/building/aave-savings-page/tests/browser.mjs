import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { encodeFunctionData, formatUnits } from './deps.mjs';
import { reserve, capFixture, funding, requestedSupplies, POOL, USDC, USDT, AUSDC, AUSDT, pool, erc20 } from './chain.mjs';
import { rpc, balance, send, advanceTime } from './rpc.mjs';
import { connect, prepareAction, submitAction, dismiss, visibleValues } from './controls.mjs';
import { CouldNotDrive } from './control-vocabulary.mjs';
import { walletWrites, walletIdle } from './rpc-policy.mjs';
import { createHarness, until } from './harness.mjs';

export const CHECKS = ['deposit_usdc', 'shows_deposit', 'shows_apy', 'withdraw_partial', 'withdraw_all',
  'deposit_usdt_leftover_allowance', 'refuses_over_cap', 'atomic_deposit'];
const here = path.dirname(fileURLToPath(import.meta.url));
const workspace = path.resolve(process.argv[2] || '/workspace');
const output = path.resolve(process.argv[3] || '/logs/verifier');
await fs.mkdir(output, { recursive: true });
const checksPath = path.join(output, 'checks.json');
const recorded = new Set();
let checks;
try { checks = JSON.parse(await fs.readFile(checksPath, 'utf8')); } catch { checks = {}; }
checks = Object.fromEntries(Object.entries(checks).filter(([name]) => name === 'compile'));
for (const check of CHECKS) checks[check] = { passed: false, reason: 'Browser journey did not complete.' };
await fs.writeFile(path.join(output, 'cap-page.txt'), 'could not drive: the cap journey did not complete\n');
const stringify = data => JSON.stringify(data, (_, value) => typeof value === 'bigint' ? value.toString() : value, 2);
const saveJson = (name, data) => fs.writeFile(path.join(output, name), stringify(data) + '\n');
const record = async (name, passed, reason) => {
  recorded.add(name);
  checks[name] = { passed: Boolean(passed), reason: reason.replace(/\s+/g, ' ').slice(0, 1200) };
  await saveJson('checks.json', checks);
};
if (checks.compile?.passed === false) {
  for (const check of CHECKS) await record(check, false, 'The project did not compile. See build.log and typecheck.log.');
  process.exit(0);
}
let harness;
let active;
const started = Date.now();

try {
  harness = await createHarness({ workspace, output, sourceContext: process.argv[4] || '/chain/chain_context.json', funding });
  const { mainRpc, account, sourceBlock } = harness;
  const initial = await capFixture(mainRpc, account.address);
  await saveJson('fixture.json', { address: account.address, sourceBlock, ...initial });
  async function reset() { await harness.reset(); active = null; }
  const capture = (s, name) => harness.capture(s, name);
  let withdrawalClock = false;
  let beforeMiningBalance;
  async function session({ atomic = false } = {}) {
    active = await harness.session({ atomic, beforeSend: async () => {
      if (withdrawalClock) {
        await advanceTime(mainRpc, 86400);
        beforeMiningBalance = await balance(mainRpc, AUSDC, account.address);
      }
    } });
    await connect(active.page, account.address);
    await until(async () => (await visibleValues(active.page, 'USDC')).percentages.length > 0, 8000);
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
      if (error.infrastructure) throw error;
      const reason = error instanceof CouldNotDrive ? error.message : `Journey failed: ${error.shortMessage || error.message}`;
      for (const name of names) if (!recorded.has(name)) await record(name, false, reason);
      await saveJson(`${names[0]}-error.json`, { error: error.stack, pageErrors: active?.errors });
      if (active) await capture(active, `${names[0]}-failure`).catch(() => {});
      if (active && names.includes('refuses_over_cap')) {
        await fs.writeFile(path.join(output, 'cap-page.txt'), `${reason}\n\n${await active.page.locator('body').innerText()}`);
        await active.page.screenshot({ path: path.join(output, 'cap-page.png'), fullPage: true }).catch(() => {});
      }
    }
  }
  async function drive(s, action, complete) {
    return submitAction(action, { settle: () => walletIdle(s.wallet), complete });
  }
  await journey(['deposit_usdc', 'shows_deposit', 'shows_apy'], async () => {
    const s = await session();
    const valuesBefore = await visibleValues(s.page, 'USDC');
    const market = await reserve(mainRpc);
    await record('shows_apy', valuesBefore.percentages.some(value => Math.abs(value - market.apy) <= 0.01), `Compounded APY ${market.apy.toFixed(6)}%; visible USDC APY values ${JSON.stringify(valuesBefore.percentages)}.`);
    const action = await prepareAction(s.page, 'USDC', 'deposit', '100');
    await drive(s, action, async () => await balance(mainRpc, AUSDC, account.address) > 99_990_000n);
    const success = await until(async () => Math.abs(Number(await balance(mainRpc, AUSDC, account.address)) - 100_000_000) <= 10_000);
    let deposited = await balance(mainRpc, AUSDC, account.address);
    await record('deposit_usdc', success, `100 USDC deposit left ${formatUnits(deposited, 6)} aUSDC.`);
    await dismiss(s.page);
    if (success) {
      await advanceTime(mainRpc, 30 * 86400);
      deposited = await balance(mainRpc, AUSDC, account.address);
      if (deposited <= 100_020_000n) throw Object.assign(new Error('Interest fixture did not exceed the display tolerance'), { infrastructure: true });
      await s.page.reload({ waitUntil: 'domcontentloaded' });
      await connect(s.page, account.address);
    }
    let values;
    const display = success && await until(async () => {
      values = await visibleValues(s.page, 'USDC');
      return values.numbers.some(value => Math.abs(value - Number(deposited) / 1e6) <= 0.01);
    });
    await record('shows_deposit', display, `aUSDC balance ${formatUnits(deposited, 6)}; visible deposit values ${JSON.stringify(values?.numbers || [])}.`);
    await capture(s, 'deposit-usdc');
  });
  // Partial and Max withdrawals have their own funded position even when deposit failed.
  if (!checks.deposit_usdc.passed) { await reset(); await seedUSDC(); }
  withdrawalClock = true;
  await journey(['withdraw_partial'], async () => {
    if (!active) await session();
    const s = active;
    await dismiss(s.page);
    const underlying = await balance(mainRpc, USDC, account.address);
    beforeMiningBalance = undefined;
    await submitAction(await prepareAction(s.page, 'USDC', 'withdraw', '40'));
    const partial = await until(async () => beforeMiningBalance !== undefined
      && Math.abs(Number(await balance(mainRpc, AUSDC, account.address) - (beforeMiningBalance - 40_000_000n))) <= 10_000
      && await balance(mainRpc, USDC, account.address) - underlying === 40_000_000n);
    await record('withdraw_partial', partial, `40 USDC withdrawal left ${formatUnits(await balance(mainRpc, AUSDC, account.address), 6)} aUSDC; returned ${formatUnits(await balance(mainRpc, USDC, account.address) - underlying, 6)} USDC.`);
    await capture(s, 'withdraw-partial');
  });
  if (!checks.withdraw_partial.passed) { await reset(); await seedUSDC(); }
  await journey(['withdraw_all'], async () => {
    const s = active || await session();
    await dismiss(s.page);
    const underlying = await balance(mainRpc, USDC, account.address);
    beforeMiningBalance = undefined;
    await submitAction(await prepareAction(s.page, 'USDC', 'withdraw', '', true));
    const closed = await until(async () => beforeMiningBalance !== undefined
      && await balance(mainRpc, AUSDC, account.address) === 0n
      && Math.abs(Number(await balance(mainRpc, USDC, account.address) - underlying - beforeMiningBalance)) <= 2);
    await record('withdraw_all', closed, `The page's withdraw-all control left ${formatUnits(await balance(mainRpc, AUSDC, account.address), 6)} aUSDC; returned ${formatUnits(await balance(mainRpc, USDC, account.address) - underlying, 6)} USDC.`);
    await capture(s, 'withdraw-all');
  });
  withdrawalClock = false;
  await reset();
  await journey(['deposit_usdt_leftover_allowance'], async () => {
    await send(mainRpc, account, { to: USDT, data: encodeFunctionData({ abi: erc20, functionName: 'approve', args: [POOL, 1_000_000n] }) });
    const allowance = BigInt(await rpc(mainRpc, 'eth_call', [{ to: USDT, data: encodeFunctionData({ abi: erc20, functionName: 'allowance', args: [account.address, POOL] }) }, 'latest']));
    if (allowance !== 1_000_000n) throw Object.assign(new Error('Leftover allowance fixture failed'), { infrastructure: true });
    const s = await session();
    await drive(s, await prepareAction(s.page, 'USDT', 'deposit', '100'), async () => await balance(mainRpc, AUSDT, account.address) > 99_990_000n);
    const success = await until(async () => Math.abs(Number(await balance(mainRpc, AUSDT, account.address)) - 100_000_000) <= 10_000);
    await record('deposit_usdt_leftover_allowance', success, `Initial Pool allowance 1 USDT; deposit left ${formatUnits(await balance(mainRpc, AUSDT, account.address), 6)} aUSDT.`);
    await capture(s, 'deposit-usdt');
  });
  await reset();
  await journey(['refuses_over_cap'], async () => {
    const market = await capFixture(mainRpc, account.address);
    const { oversized } = market;
    const s = await session();
    const before = s.wallet.requests.length;
    const action = await prepareAction(s.page, 'USDC', 'deposit', formatUnits(oversized, 6), false, { allowRefusal: true });
    await drive(s, action, async () => false);
    const idle = await walletIdle(s.wallet);
    const requests = walletWrites(s.wallet.requests.slice(before));
    const supplies = requestedSupplies(requests);
    await record('refuses_over_cap', checks.deposit_usdc.passed && requests.length === 0, `Asked for ${formatUnits(oversized, 6)} USDC with ${formatUnits(market.room, 6)} room; successful in-room deposit ${checks.deposit_usdc.passed}; wallet writes ${requests.map(request => request.method).join(', ') || 'none'}; idle ${idle}.`);
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
    await drive(s, action, async () => await balance(mainRpc, AUSDC, account.address) > 99_990_000n);
    const deposited = await until(async () => Math.abs(Number(await balance(mainRpc, AUSDC, account.address)) - 100_000_000) <= 10_000);
    const requests = s.wallet.requests.slice(before);
    await walletIdle(s.wallet);
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
  if (error.pageFailure) {
    for (const check of CHECKS) if (!recorded.has(check)) await record(check, false, `Page setup failed: ${error.message}`);
  } else {
    console.error(error);
    process.exitCode = 1;
  }
} finally {
  if (harness) await harness.close();
  await saveJson('checks.json', checks);
  await saveJson('timing.json', { browserSeconds: (Date.now() - started) / 1000 });
}
