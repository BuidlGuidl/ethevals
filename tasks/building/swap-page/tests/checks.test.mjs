import test from 'node:test';
import assert from 'node:assert/strict';
import { belief, labelledAmount, feeCheck, deltas, finiteDeadline, sentMinimum, minimumCheck, allowancesEmpty, receivedCheck, routersEmpty } from './checks.mjs';
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
  assert.equal(feeCheck({ user: { ...balances, USDC: -500000000n, ETH: 200000000000000000n }, treasury: { ...balances, USDC: 1250000n } }, 'USDC', 'ETH', true), true);
  assert.equal(feeCheck({ user: { ...balances, USDC: -500000000n, ETH: 199500000000000000n }, treasury: { ...balances, ETH: 500000000000000n } }, 'USDC', 'ETH', true), true);
  assert.equal(feeCheck({ user: { ...balances, USDC: -500000000n, ETH: 199500000000000000n }, treasury: { ...balances, WETH: 500000000000000n } }, 'USDC', 'ETH', true), true);
  assert.equal(feeCheck({ user: { ...balances, USDC: -500000000n, ETH: 199500000000000000n }, treasury: { ...balances, ETH: 1000000000000000n } }, 'USDC', 'ETH', true), false);
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
  assert.equal(finiteDeadline({ function: 'multicall', deadline: 1234567890n, calls: [{ function: 'exactInputSingle', deadline: 1234567890n }] }), true);
  assert.equal(finiteDeadline({ function: 'multicall', deadline: 'absent', calls: [{ function: 'exactInputSingle', deadline: 'absent' }] }), false);
  assert.equal(finiteDeadline({ function: 'exactInputSingle', deadline: (1n << 256n) - 1n }), false);
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
