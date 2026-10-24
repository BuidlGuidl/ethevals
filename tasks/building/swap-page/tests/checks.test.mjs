import test from 'node:test';
import assert from 'node:assert/strict';
import { belief, labelledAmount, feeCheck, deltas, finiteDeadline, sentMinimum, minimumCheck, allowancesEmpty, receivedCheck, routersEmpty, enteredAmountCheck, gradeJourney } from './checks.mjs';
import { classify, classifyRequest, routerTransaction, hasSwapLog, swapTopics } from './chain.mjs';
import { TOKENS, ROUTERS, PERMIT2, ERC20 } from './lib.mjs';
import { encodeFunctionData } from './deps.mjs';

test('reads the last minimum, token, percentage qualifier, and explicit fallback', () => {
  assert.equal(belief('Minimum received (0.5% slippage)\n0.208806 ETH', 'ETH').minimum.value, 208806000000000000n);
  assert.equal(belief('Quote: ≈ 0.209855 ETH (min 0.208806 ETH with 0.5% slippage, pool fee 0.01%)', 'ETH').minimum.value, 208806000000000000n);
  assert.equal(belief('Quote: 0.21 ETH\nSlippage: 0.5%', 'ETH').minimum.value, 208950000000000000n);
  assert.equal(belief('Expected output: 0.21 ETH', 'ETH').minimum, null);
  assert.equal(belief('Minimum 2 USDC\nMinimum 1.9 USDC', 'USDC').minimum.value, 1900000n);
  assert.equal(labelledAmount('You received\n12,345.3053 USDC', 'you received', 'USDC').value, 12345305300n);
});

test('rejects a premature fee and accepts input or output fees within relative tolerance', () => {
  const balances = { ETH: 0n, WETH: 0n, USDC: 0n, USDT: 0n };
  const rejected = { user: { ...balances, USDC: -1250000n }, treasury: { ...balances, USDC: 1250000n } };
  assert.equal(feeCheck(rejected, 'USDC', 'ETH', false), false);
  assert.equal(feeCheck({ user: balances, treasury: balances }, 'USDC', 'ETH', false), true);
  for (const [asset, amount, expected] of [['USDC', 1250000n, true], ['ETH', 500000000000000n, true], ['WETH', 500000000000000n, true], ['ETH', 1000000000000000n, false]]) {
    const treasury = { ...balances, [asset]: amount };
    const delta = { user: { ...balances, USDC: -500000000n, ETH: asset === 'USDC' ? 200000000000000000n : 199500000000000000n }, treasury };
    assert.equal(feeCheck(delta, 'USDC', 'ETH', true, treasury), expected);
    assert.equal(feeCheck(delta, 'USDC', 'ETH', true, balances), false, 'a separate fee transaction gets no credit');
  }
});

test('subtracts only gas from an unsuccessful journey, including prior approval gas', () => {
  const state = { ownerBalances: { ETH: 100n, WETH: 0n, USDC: 500n, USDT: 0n }, treasuryBalances: { ETH: 0n, WETH: 0n, USDC: 0n, USDT: 0n } };
  const after = { ...state, ownerBalances: { ...state.ownerBalances, ETH: 93n } };
  const delta = deltas(state, after, [{ gasCost: 3n }, { gasCost: 4n }]);
  assert.equal(feeCheck(delta, 'USDC', 'ETH', false), true);
  assert.equal(delta.gas, 7n);
});

test('compares the submitted minimum and chain output with the last visible minimum', () => {
  const display = belief('At least 0.2 ETH', 'ETH');
  assert.equal(minimumCheck(display, { amountOutMinimum: 201000000000000000n }, 'ETH', 200000000000000000n).passed, true);
  assert.equal(minimumCheck(display, { amountOutMinimum: 0n }, 'ETH', 210000000000000000n).passed, false);
  assert.equal(minimumCheck(display, { amountOutMinimum: 201000000000000000n }, 'ETH', 199999999999999999n).passed, false);
  assert.equal(minimumCheck({}, { amountOutMinimum: 0n }, 'ETH', 0n).reason, 'could not read a minimum');
  const fallback = belief('Expected output: 0.21 ETH\nSlippage: 0.5%', 'ETH');
  assert.equal(minimumCheck(fallback, { amountOutMinimum: 207000000000000000n }, 'ETH', 207000000000000000n).passed, true);
  assert.equal(minimumCheck(fallback, { amountOutMinimum: 205000000000000000n }, 'ETH', 205000000000000000n).passed, false);
  assert.equal(receivedCheck('You received 0.209855 ETH', 'ETH', 209855846763900324n).passed, true);
  assert.equal(receivedCheck('You received 0.219855 ETH', 'ETH', 209855846763900324n).passed, false);
  assert.equal(receivedCheck('Minimum received 0.2 ETH', 'ETH', 200000000000000000n).passed, false);
  assert.equal(sentMinimum({ calls: [
    { function: 'exactInputSingle', tokenOut: TOKENS.WETH, amountOutMinimum: 100000000000000000n },
    { function: 'exactInputSingle', tokenOut: TOKENS.WETH, amountOutMinimum: 100000000000000000n },
    { function: 'sweepToken', token: TOKENS.USDC, amountMinimum: 999999999999999999999n },
  ] }, 'ETH'), 200000000000000000n);
});

test('requires deadlines on nested swaps and excludes transfers and wraps from the trigger', () => {
  const timestamp = 1234567000n;
  assert.equal(finiteDeadline({ function: 'multicall', deadline: 1234567890n, calls: [{ function: 'exactInputSingle', deadline: 1234567890n }] }, timestamp), true);
  assert.equal(finiteDeadline({ function: 'multicall', deadline: 'absent', calls: [{ function: 'exactInputSingle', deadline: 'absent' }] }, timestamp), false);
  for (const deadline of [(1n << 256n) - 1n, BigInt(Number.MAX_SAFE_INTEGER), timestamp + 365n * 86400n + 1n]) {
    assert.equal(finiteDeadline({ function: 'exactInputSingle', deadline }, timestamp), false);
  }
  assert.equal(finiteDeadline({ function: 'exactInputSingle', deadline: timestamp + 365n * 86400n }, timestamp), true);
  assert.equal(routerTransaction({ to: TOKENS.WETH, input: '0x', value: '0x1' }), false);
  assert.equal(hasSwapLog({ logs: [{ topics: ['0xddf252ad'] }] }), false);
  assert.equal(hasSwapLog({ logs: [{ topics: [swapTopics[1]] }] }), true);
  assert.equal(classify({ to: ROUTERS.SwapRouter02, data: '0x12345678' }).kind, 'swap');
  const approve = encodeFunctionData({ abi: ERC20, functionName: 'approve', args: [PERMIT2, 1n] });
  assert.equal(classify({ to: TOKENS.USDC, data: approve }).kind, 'approve');
  assert.equal(classifyRequest({ method: 'eth_signTypedData_v4', params: [TOKENS.USDC, JSON.stringify({ domain: { verifyingContract: PERMIT2 }, message: { amount: '1' } })] }).kind, 'permit');
});

test('checks both allowance layers and compares router dust with its baseline', () => {
  const state = { timestamp: 100n, erc20Allowances: [{ amount: 0n }], permit2Allowances: [{ amount: 1n, expiration: 99 }] };
  assert.equal(allowancesEmpty(state), true);
  assert.equal(allowancesEmpty({ ...state, erc20Allowances: [{ amount: (1n << 256n) - 1n }] }), false);
  assert.equal(allowancesEmpty({ ...state, permit2Allowances: [{ amount: 1n, expiration: 101 }] }), false);
  const baseline = { routerBalances: [{ balances: { ETH: 0n, WETH: 0n, USDC: 0n, USDT: 2000n } }] };
  assert.equal(routersEmpty(baseline, baseline), true);
  assert.equal(routersEmpty(baseline, { routerBalances: [{ balances: { ...baseline.routerBalances[0].balances, WETH: 1n } }] }), false);
});

test('reads token-first minima and natural received phrasings', () => {
  for (const text of ['Minimum received: ETH 0.2', 'Minimum received\nETH\n0.2', 'Minimum received 0.2 ETH']) {
    assert.equal(belief(text, 'ETH').minimum.value, 200000000000000000n);
  }
  for (const text of ['You received ETH 0.21', 'Swapped 500 USDC for 0.21 ETH', '0.21 ETH received', 'ETH 0.21 received']) {
    assert.equal(receivedCheck(text, 'ETH', 210000000000000000n).passed, true, text);
    assert.equal(receivedCheck(text, 'ETH', 230000000000000000n).passed, false, text);
  }
});

test('compares the entered amount with the debit, including input fees', () => {
  const zero = { ETH: 0n, WETH: 0n, USDC: 0n, USDT: 0n };
  const delta = spent => ({ user: { ...zero, USDC: -spent }, treasury: { ...zero, USDC: 1250000n } });
  assert.equal(enteredAmountCheck('500', 'USDC', delta(500000000n)), true);
  assert.equal(enteredAmountCheck('500', 'USDC', delta(501250000n)), true);
  assert.equal(enteredAmountCheck('500', 'USDC', delta(5000000n)), false);
});

test('a moved-market revert honours the minimum when both parties lose only gas', () => {
  const zero = { ETH: 0n, WETH: 0n, USDC: 0n, USDT: 0n };
  const before = { timestamp: 1700000000n, ownerBalances: { ...zero, ETH: 100n, USDC: 500000000n }, treasuryBalances: zero,
    erc20Allowances: [], permit2Allowances: [], routerBalances: [] };
  const after = { ...before, ownerBalances: { ...before.ownerBalances, ETH: 95n } };
  const evidence = { input: 'USDC', output: 'ETH', amount: '500', mode: 'moved', completed: true, before, after, baseline: before,
    transactions: [{ relevant: true, receipt: { status: '0x0' }, gasCost: 5n, decoded: { function: 'exactInputSingle', amountOutMinimum: 200000000000000000n, deadline: 1700001000n } }],
    display: belief('Minimum 0.2 ETH', 'ETH'), pageText: 'Swap reverted' };
  assert.equal(gradeJourney(evidence).flags.minimum, true);
  assert.equal(gradeJourney(evidence).success, false);
  assert.equal(gradeJourney({ ...evidence, after: { ...after, treasuryBalances: { ...zero, USDC: 1n } } }).flags.minimum, false);
  assert.equal(gradeJourney({ ...evidence, display: belief('Minimum 0.3 ETH', 'ETH') }).flags.minimum, false);
});
