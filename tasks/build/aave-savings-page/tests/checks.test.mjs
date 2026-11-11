import test from 'node:test';
import assert from 'node:assert/strict';
import { gradeSavings } from './checks.mjs';

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
    typed: [{ value: '100', time: 500 }, { value: '6000.10', time: 4_000 }],
    requests: [
      { method: 'eth_requestAccounts', time: 100 },
      { method: 'eth_sendTransaction', time: 600 },
      { method: 'eth_call', time: 4_500 },
    ],
    end: 9_000,
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

test('the cap check fails when no amount above the room was ever entered', () => {
  const run = session();
  run.typed = [{ value: '100', time: 500 }];
  assert.deepEqual(gradeSavings(run).refuses_over_cap, { passed: false,
    reason: 'No amount above the room left under the lowered supply cap was entered on the page.' });
});

test('the cap check fails when the page asks the wallet after an amount above the room is entered', () => {
  const run = session();
  run.requests.push({ method: 'eth_sendTransaction', time: 5_000 });
  assert.deepEqual(gradeSavings(run).refuses_over_cap, { passed: false,
    reason: 'Entered 6000.10 USDC with 3647.670000 room; in-room deposit true; wallet writes after entering it: eth_sendTransaction.' });
});

test('a wallet request after the amount is changed back inside the room does not count against the cap check', () => {
  const run = session();
  run.typed.push({ value: '10', time: 6_000 });
  run.requests.push({ method: 'eth_sendTransaction', time: 7_000 });
  assert.equal(gradeSavings(run).refuses_over_cap.passed, true);
  run.requests.push({ method: 'personal_sign', time: 5_000 });
  assert.equal(gradeSavings(run).refuses_over_cap.passed, false);
});

test('an amount above the room counts only after the cap was lowered', () => {
  const run = session();
  run.typed = [{ value: '6,000.10', time: 2_500 }, { value: '6,000.10', time: 4_000 }];
  run.requests.push({ method: 'eth_sendTransaction', time: 2_600 });
  assert.equal(gradeSavings(run).refuses_over_cap.passed, true);
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
