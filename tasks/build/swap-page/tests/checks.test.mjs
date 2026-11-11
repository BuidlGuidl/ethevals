import test from 'node:test';
import assert from 'node:assert/strict';
import { gradeSwap, gradeSession, feeCheck, finiteDeadline, enteredAmountCheck, allowancesEmpty } from './checks.mjs';
import { swapTopics } from './chain.mjs';
import { TOKENS } from './lib.mjs';

const balances = () => Object.fromEntries(Object.keys(TOKENS).map(symbol => [symbol, 0n]));
const state = () => ({ ownerBalances: balances(), treasuryBalances: balances(), timestamp: 100n,
  erc20Allowances: [], permit2Allowances: [], routerBalances: [] });

const record = (input, output, mode = 'normal') => ({ input, output, mode, amount: '1', success: true, entered: true,
  flags: { fee: true, approvals: true, deadline: true, native: true, routers: true } });
const covered = () => [record('ETH', 'USDC'), record('USDC', 'ETH'), record('USDT', 'USDC'), record('USDT', 'USDC', 'seed'),
  { ...record('USDC', 'ETH', 'reject'), success: false, rejected: true },
  { ...record('USDC', 'ETH', 'race'), success: false, marketResult: { moved: true } }];
const decisions = records => Object.fromEntries(Object.entries(records).map(([name, check]) => [name, check.passed]));
const compile = { compile: { passed: true, reason: 'The project compiled.' } };

test('a covered session with a rejection and price race passes every record', () => {
  assert.deepEqual(decisions(gradeSession(covered(), [], compile)), { compile: true, swaps_assets: true,
    cut_only_on_swap: true, exact_approvals: true, finite_deadline: true, native_eth: true, routers_empty: true });
});

test('every normal or seeded swap must succeed, even when successful swaps cover every pair', () => {
  const tests = [...covered(), { ...record('ETH', 'USDC'), success: false }];
  assert.equal(gradeSession(tests, [], compile).swaps_assets.passed, false);
  assert.equal(gradeSession(covered(), [], compile).swaps_assets.passed, true);
});

test('unannounced writes, wrong entered amounts, missing pairs, and a missing seed each fail swaps_assets', () => {
  const tests = covered();
  assert.equal(gradeSession(tests, [{ unannounced: true }], compile).swaps_assets.passed, false);
  tests[0].entered = false;
  assert.equal(gradeSession(tests, [], compile).swaps_assets.passed, false);
  assert.equal(gradeSession(covered().filter(test => test.input !== 'ETH'), [], compile).swaps_assets.passed, false);
  assert.equal(gradeSession(covered().filter(test => test.mode !== 'seed'), [], compile).swaps_assets.passed, false);
});

test('the fee check requires an actual rejection, a price race, and unchanged funds in each failed swap', () => {
  assert.equal(gradeSession(covered().filter(test => test.mode !== 'reject'), [], compile).cut_only_on_swap.passed, false);
  assert.equal(gradeSession(covered().filter(test => test.mode !== 'race'), [], compile).cut_only_on_swap.passed, false);
  const tests = covered();
  tests[4].rejected = false;
  assert.equal(gradeSession(tests, [], compile).cut_only_on_swap.passed, false);
  tests[4].rejected = true;
  tests[5].flags.fee = false;
  assert.equal(gradeSession(tests, [], compile).cut_only_on_swap.passed, false);
});

test('one bad approval, deadline, native output, or router balance fails its own session record', () => {
  const tests = covered();
  Object.assign(tests[0].flags, { approvals: false, deadline: false, native: false, routers: false });
  assert.deepEqual(decisions(gradeSession(tests, [], compile)), { compile: true, swaps_assets: true,
    cut_only_on_swap: true, exact_approvals: false, finite_deadline: false, native_eth: false, routers_empty: false });
});

test('an empty session fails every swap record with a reason', () => {
  assert.deepEqual(gradeSession([], [], {}), Object.fromEntries([
    'swaps_assets', 'cut_only_on_swap', 'exact_approvals', 'finite_deadline', 'native_eth', 'routers_empty',
  ].map(name => [name, { passed: false, reason: 'No swaps came from the page.' }])));
  assert.deepEqual(decisions(gradeSession(covered().filter(test => !test.success), [], {})), {
    swaps_assets: false, cut_only_on_swap: false, exact_approvals: false, finite_deadline: false, native_eth: false, routers_empty: false });
});

test('a compile failure fails every swap record even with stale successful transactions', () => {
  const records = gradeSession(covered(), [], { compile: { passed: false, reason: 'Build failed.' } });
  assert.deepEqual(decisions(records), { compile: false, swaps_assets: false, cut_only_on_swap: false,
    exact_approvals: false, finite_deadline: false, native_eth: false, routers_empty: false });
  assert.equal(records.swaps_assets.reason, 'The project did not compile. See build.log and typecheck.log.');
});

test('a successful ETH swap pays its fee in the swap transaction and spends the entered amount', () => {
  const before = state();
  before.ownerBalances.ETH = 10n ** 19n;
  const after = state();
  after.ownerBalances.ETH = 9n * 10n ** 18n;
  after.ownerBalances.USDC = 399n * 10n ** 6n;
  after.treasuryBalances.USDC = 10n ** 6n;
  const treasuryDelta = { ...balances(), USDC: 10n ** 6n };
  const tx = { relevant: true, gasCost: 0n, treasuryDelta,
    receipt: { status: '0x1', logs: [{ topics: [swapTopics[0]] }] },
    decoded: { function: 'exactInput', deadline: 200n } };
  const result = gradeSwap({ input: 'ETH', output: 'USDC', amount: '1', mode: 'normal',
    before, after, baseline: before, transactions: [tx] });
  assert.deepEqual({ success: result.success, entered: result.entered, flags: result.flags }, {
    success: true, entered: true, flags: { fee: true, approvals: true, deadline: true, native: true, routers: true } });
  assert.equal(gradeSwap({ input: 'ETH', output: 'USDC', amount: '2', mode: 'normal',
    before, after, baseline: before, transactions: [tx] }).entered, false);
  assert.equal(gradeSwap({ input: 'ETH', output: 'USDC', amount: '1', mode: 'normal',
    before, after, baseline: before, transactions: [{ ...tx, treasuryDelta: balances() }] }).flags.fee, false);
});

test('canceled and reverted swaps can lose gas but cannot pay a treasury fee', () => {
  const before = state();
  before.ownerBalances.ETH = 1000n;
  const after = state();
  after.ownerBalances.ETH = 990n;
  const tx = { relevant: true, gasCost: 10n, receipt: { status: '0x0', logs: [] },
    decoded: { function: 'exactInput', deadline: 200n } };
  const args = { input: 'USDC', output: 'ETH', amount: '500', mode: 'race',
    before, after, baseline: before, transactions: [tx], marketResult: { moved: true } };
  assert.equal(gradeSwap(args).flags.fee, true);
  after.treasuryBalances.USDC = 1n;
  assert.equal(gradeSwap(args).flags.fee, false);
  assert.equal(feeCheck({ user: balances(), treasury: balances() }, 'USDC', 'ETH', false), true);
});

test('WETH output, retained permissions, router funds, and unbounded deadlines fail their own checks', () => {
  const before = state();
  before.ownerBalances.USDC = 500000000n;
  before.routerBalances = [{ balances: balances() }];
  const after = state();
  after.ownerBalances.WETH = 10n ** 18n;
  after.routerBalances = [{ balances: { ...balances(), ETH: 1n } }];
  after.erc20Allowances = [{ amount: 1n }];
  const tx = { relevant: true, gasCost: 0n, treasuryDelta: balances(),
    receipt: { status: '0x1', logs: [{ topics: [swapTopics[0]] }] }, decoded: { function: 'exactInput' } };
  const result = gradeSwap({ input: 'USDC', output: 'ETH', amount: '500', mode: 'normal',
    before, after, baseline: before, transactions: [tx] });
  assert.deepEqual(result.flags, { fee: false, approvals: false, deadline: false, native: false, routers: false });
  assert.equal(allowancesEmpty({ erc20Allowances: [], permit2Allowances: [{ amount: 1n, expiration: 99n }], timestamp: 100n }), true);
  assert.equal(allowancesEmpty({ erc20Allowances: [], permit2Allowances: [{ amount: 1n, expiration: 101n }], timestamp: 100n }), false);
  assert.equal(finiteDeadline({ function: 'exactInput', deadline: 101n }, 100n), true);
  assert.equal(finiteDeadline({ function: 'exactInput', deadline: 2n ** 255n }, 100n), false);
});
