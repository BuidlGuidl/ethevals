import test from 'node:test';
import assert from 'node:assert/strict';
import { gradeSwap, feeCheck, finiteDeadline, enteredAmountCheck, allowancesEmpty } from './checks.mjs';
import { swapTopics } from './chain.mjs';
import { TOKENS } from './lib.mjs';

const balances = () => Object.fromEntries(Object.keys(TOKENS).map(symbol => [symbol, 0n]));
const state = () => ({ ownerBalances: balances(), treasuryBalances: balances(), timestamp: 100n,
  erc20Allowances: [], permit2Allowances: [], routerBalances: [] });

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
