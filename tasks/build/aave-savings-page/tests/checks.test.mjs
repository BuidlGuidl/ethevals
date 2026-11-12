import test from 'node:test';
import assert from 'node:assert/strict';
import { gradeSavings } from './checks.mjs';
import { encodeFunctionData } from './deps.mjs';
import { POOL, USDC, USDT, pool, erc20 } from './chain.mjs';

const U = 1_000_000n;
const zero = { usdc: 10_000n * U, usdt: 10_000n * U, ausdc: 0n, ausdt: 0n };
const move = (hash, block, before, change) => ({ hash: hash.padEnd(66, '0'), status: '0x1', block, before,
  after: Object.fromEntries(Object.entries(before).map(([key, value]) => [key, value + (change[key] || 0n)])) });
const passed = checks => Object.fromEntries(Object.entries(checks).map(([name, check]) => [name, check.passed]));

// One page session the way a careful page and a thorough judge produce it.
function session() {
  const deposited = { ...zero, usdc: zero.usdc - 100n * U, ausdc: 100n * U };
  const grown = { ...deposited, ausdc: 100_330_000n };
  const partial = { ...grown, usdc: grown.usdc + 40n * U, ausdc: 60_340_000n };
  return {
    compile: true,
    moves: [
      move('0xa1', 10, zero, { usdc: -100n * U, ausdc: 100n * U - 1n }),
      move('0xa2', 12, grown, { usdc: 40n * U, ausdc: -40n * U }),
      move('0xa3', 14, partial, { usdc: 60_340_000n, ausdc: -60_340_000n }),
      move('0xa4', 17, zero, { usdt: -100n * U, ausdt: 100n * U }),
    ],
    conditions: [
      { kind: 'move-time', days: 30, block: 11, time: 1_000 },
      { kind: 'old-usdt-approval', block: 16, time: 2_000 },
      { kind: 'full-cap', room: (3_647_670_000n).toString(), block: 18, time: 3_000 },
    ],
    requests: [
      { method: 'eth_requestAccounts', time: 100 },
      { method: 'eth_sendTransaction', time: 600 },
      { method: 'eth_call', time: 4_500 },
    ],
  };
}

test('a careful page passes every chain check', () => {
  assert.deepEqual(passed(gradeSavings(session())), {
    deposit_usdc: true, withdraw_partial: true, withdraw_all: true, deposit_usdt_leftover_allowance: true, refuses_over_cap: true,
  });
});

test('a Max that sends the last balance read fails, even when a second Max sweeps the dust', () => {
  const run = session();
  const partial = run.moves[2].before;
  const dust = { ...partial, usdc: partial.usdc + 60_336_156n, ausdc: 6_595n };
  run.moves.splice(2, 1,
    move('0xb1', 14, partial, { usdc: 60_336_156n, ausdc: -60_333_561n }),
    move('0xb2', 15, dust, { usdc: 6_595n, ausdc: -6_595n }));
  const checks = gradeSavings(run);
  assert.equal(checks.withdraw_all.passed, false);
  assert.equal(checks.withdraw_partial.passed, true);
});

test('the cap check cannot pass without the full-cap command', () => {
  const run = session();
  run.conditions = run.conditions.filter(condition => condition.kind !== 'full-cap');
  assert.deepEqual(gradeSavings(run).refuses_over_cap, { passed: false,
    reason: 'The session never lowered the USDC supply cap.' });
});

const supply = (amount, asset = USDC) => ({ to: POOL,
  data: encodeFunctionData({ abi: pool, functionName: 'supply', args: [asset, amount, POOL, 0] }) });
const approval = (amount, spender = POOL) => ({ to: USDC,
  data: encodeFunctionData({ abi: erc20, functionName: 'approve', args: [spender, amount] }) });

for (const method of ['eth_sendTransaction', 'wallet_sendTransaction', 'wallet_sendCalls']) {
test(`an over-room supply in ${method} fails despite empty or unrelated typing records`, () => {
  const run = session();
  const call = supply(6000_100_000n);
  run.requests.push({ method, params: method === 'wallet_sendCalls' ? [{ calls: [call] }] : [call], time: 5_000, error: 'reverted' });
  run.typed = [{ value: '6000.10', time: 4_000 }, { value: '', time: 4_100 }, { value: 'search', time: 4_200 }];
  assert.deepEqual(gradeSavings(run).refuses_over_cap, { passed: false,
    reason: 'In-room deposit true; wallet requests above the lowered USDC cap: supply 6000.100000 USDC with 3647.670000 room.' });
});
}

test('an over-room Pool approval fails even without a supply request', () => {
  const run = session();
  run.requests.push({ method: 'wallet_sendCalls', params: [{ calls: [approval(6000_100_000n)] }], time: 5_000 });
  assert.deepEqual(gradeSavings(run).refuses_over_cap, { passed: false,
    reason: 'In-room deposit true; wallet requests above the lowered USDC cap: approve 6000.100000 USDC with 3647.670000 room.' });
});

test('Withdraw all and prefilled in-room deposits after full-cap do not fail the cap check', () => {
  const run = session();
  run.requests.push({ method: 'wallet_sendCalls', time: 5_000, params: [{ calls: [
    { to: POOL, data: encodeFunctionData({ abi: pool, functionName: 'withdraw', args: [USDC, 2n ** 256n - 1n, POOL] }) },
    approval(100n * U), supply(100n * U), supply(6000n * U, USDT), approval(6000n * U, USDT),
  ] }] });
  assert.deepEqual(gradeSavings(run).refuses_over_cap, { passed: true,
    reason: 'In-room deposit true; wallet requests above the lowered USDC cap: none.' });
});

test('the cap check uses the latest preceding room and ignores requests before full-cap', () => {
  const run = session();
  run.requests.push({ method: 'eth_sendTransaction', params: [supply(6000n * U)], time: 2_900 });
  run.conditions.push({ kind: 'full-cap', time: 4_500, room: String(7000n * U) });
  run.requests.push({ method: 'eth_sendTransaction', params: [supply(6000n * U)], time: 5_000 });
  assert.equal(gradeSavings(run).refuses_over_cap.passed, true);
  run.requests.push({ method: 'eth_sendTransaction', params: [supply(6000n * U)], time: 4_000 });
  assert.equal(gradeSavings(run).refuses_over_cap.passed, false);
});

test('a USDT deposit counts only when it follows the leftover approval', () => {
  const run = session();
  run.moves[3].block = 15;
  const checks = gradeSavings(run);
  assert.equal(checks.deposit_usdt_leftover_allowance.passed, false);
  run.conditions = run.conditions.filter(condition => condition.kind !== 'old-usdt-approval');
  assert.deepEqual(gradeSavings(run).deposit_usdt_leftover_allowance,
    { passed: false, reason: 'The session never left a 1 USDT approval to the Pool.' });
});

test('a reverted transaction and a deposit of another amount do not count as the 100 USDC deposit', () => {
  const run = session();
  run.moves[0] = { ...move('0xc1', 10, zero, { usdc: -100n * U, ausdc: 100n * U }), status: '0x0' };
  run.moves.push(move('0xc2', 20, zero, { usdc: -99n * U, ausdc: 99n * U }));
  const checks = gradeSavings(run);
  assert.equal(checks.deposit_usdc.passed, false);
  assert.equal(checks.refuses_over_cap.passed, false);
});

test('a project that does not compile fails every chain check', () => {
  assert.deepEqual(gradeSavings({ compile: false }).withdraw_all,
    { passed: false, reason: 'The project did not compile. See build.log and typecheck.log.' });
});
