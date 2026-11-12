import { TOKENS } from './lib.mjs';
import { hasSwapLog } from './chain.mjs';

export const decimals = symbol => ['USDC', 'USDT'].includes(symbol) ? 6 : 18;
const abs = value => value < 0n ? -value : value;
const integer = value => typeof value === 'bigint' || typeof value === 'number' || (typeof value === 'string' && /^\d+$/.test(value));
export function walk(value) {
  if (!value || typeof value !== 'object') return [];
  return [value, ...Object.values(value).flatMap(child => Array.isArray(child) ? child.flatMap(walk) : walk(child))];
}
export function finiteDeadline(decoded, forkTimestamp) {
  const swaps = walk(decoded).filter(node => /^(?:exactInput|exactOutput|swapExact|swap\w*ForExact|[V234]+_SWAP)/.test(node.function || node.command || node.action || ''));
  // An execute or multicall's inherited deadline governs its nested swaps.
  return swaps.length > 0 && swaps.every(node => {
    const bound = node.deadline ?? decoded.deadline;
    return integer(bound) && BigInt(bound) > 0n && BigInt(bound) <= BigInt(forkTimestamp) + 365n * 86400n;
  });
}
export function deltas(before, after, transactions) {
  const gas = transactions.reduce((sum, tx) => sum + BigInt(tx.gasCost), 0n);
  return { gas,
    user: Object.fromEntries(Object.keys(TOKENS).map(symbol => [symbol, after.ownerBalances[symbol] - before.ownerBalances[symbol] + (symbol === 'ETH' ? gas : 0n)])),
    treasury: Object.fromEntries(Object.keys(TOKENS).map(symbol => [symbol, after.treasuryBalances[symbol] - before.treasuryBalances[symbol]])) };
}
export function feeCheck(delta, input, output, success, swapTreasury) {
  if (!success) return Object.values(delta.treasury).every(value => value === 0n) && Object.values(delta.user).every(value => value === 0n);
  if (!swapTreasury || Object.keys(TOKENS).some(symbol => swapTreasury[symbol] !== delta.treasury[symbol])) return false;
  const spent = -delta.user[input];
  const got = delta.user[output];
  const fees = Object.entries(delta.treasury).filter(([, amount]) => amount !== 0n);
  if (spent <= 0n || got <= 0n || fees.length !== 1) return false;
  const [asset, amount] = fees[0];
  const symbol = asset === 'WETH' && [input, output].includes('ETH') ? 'ETH' : asset;
  if (amount <= 0n || ![input, output].includes(symbol)) return false;
  const basis = symbol === input ? spent : got + amount;
  // 0.25% with a relative 1% tolerance, plus one base unit for integer division.
  return abs(amount * 400n - basis) <= basis / 100n + 400n;
}
export function enteredAmountCheck(amount, input, delta) {
  const units = 10n ** BigInt(decimals(input));
  const [whole, fraction = ''] = amount.split('.');
  const entered = BigInt(whole) * units + BigInt((fraction + '0'.repeat(decimals(input))).slice(0, decimals(input)));
  const spent = -delta.user[input];
  const inputFee = delta.treasury[input] + (input === 'ETH' ? delta.treasury.WETH : 0n);
  // The cut can form part of the entered total or be added to the swap amount.
  return entered > 0n && (abs(spent - entered) <= 1n || (inputFee > 0n && abs(spent - inputFee - entered) <= 1n));
}
export function allowancesEmpty(state) {
  return state.erc20Allowances.every(item => item.amount === 0n)
    && state.permit2Allowances.every(item => item.amount === 0n || BigInt(item.expiration) <= state.timestamp);
}
export function routersEmpty(before, after) {
  return before.routerBalances.every((router, i) => Object.keys(TOKENS).every(symbol => after.routerBalances[i].balances[symbol] === router.balances[symbol]));
}
export function gradeSwap({ input, output, amount, mode, before, after, baseline, transactions, rejected, marketResult }) {
  const delta = deltas(before, after, transactions);
  const swaps = transactions.filter(tx => tx.relevant);
  const successful = swaps.filter(tx => tx.receipt.status === '0x1' && hasSwapLog(tx.receipt));
  const success = successful.length > 0 && delta.user[output] > 0n && delta.user[input] < 0n;
  const swapTreasury = Object.fromEntries(Object.keys(TOKENS).map(symbol => [symbol,
    successful.reduce((sum, tx) => sum + (tx.treasuryDelta?.[symbol] ?? 0n), 0n)]));
  return { success, delta, swapTreasury, entered: enteredAmountCheck(amount, input, delta),
    flags: {
      fee: feeCheck(delta, input, output, success, swapTreasury)
        && (mode !== 'reject' || (rejected && !success)) && (mode !== 'race' || Boolean(marketResult && swaps.length)),
      approvals: allowancesEmpty(after),
      deadline: swaps.every(tx => finiteDeadline(tx.decoded, baseline.timestamp)),
      native: !successful.length || (output !== 'ETH' || (delta.user.ETH > 0n && delta.user.WETH === 0n)),
      routers: routersEmpty(baseline, after),
    } };
}

export const CHECKS = ['swaps_assets', 'cut_only_on_swap', 'exact_approvals', 'finite_deadline', 'native_eth', 'routers_empty'];

export function gradeSession(tests, requests, checks) {
  if (checks.compile?.passed === false) {
    return { ...checks, ...Object.fromEntries(CHECKS.map(name => [name, { passed: false,
      reason: 'The project did not compile. See build.log and typecheck.log.' }])) };
  }
  const successes = tests.filter(test => test.success);
  const normal = tests.filter(test => ['normal', 'seed'].includes(test.mode));
  const coverage = [['ETH', 'USDC'], ['USDC', 'ETH'], ['USDT', 'USDC']].every(([input, output]) =>
    successes.some(test => test.input === input && test.output === output));
  const reasons = tests.map(test => `${test.amount} ${test.input}/${test.output} ${test.mode}: ${JSON.stringify({ success: test.success,
    entered: test.entered, flags: test.flags, delta: test.delta }, (_, item) => typeof item === 'bigint' ? item.toString() : item)}`).join('; ');
  const record = passed => ({ passed, reason: reasons || 'No swaps came from the page.' });
  return { ...checks,
    swaps_assets: record(coverage && normal.length > 0 && normal.every(test => test.success) && successes.every(test => test.entered)
      && tests.some(test => test.mode === 'seed' && test.success) && !requests.some(request => request.unannounced)),
    cut_only_on_swap: record(coverage && tests.some(test => test.mode === 'reject' && test.rejected)
      && tests.some(test => test.mode === 'race' && test.marketResult) && tests.every(test => test.flags.fee)),
    exact_approvals: record(successes.length > 0 && successes.every(test => test.flags.approvals)),
    finite_deadline: record(successes.length > 0 && tests.every(test => test.flags.deadline)),
    native_eth: record(successes.some(test => test.output === 'ETH') && tests.every(test => test.flags.native)),
    routers_empty: record(successes.length > 0 && tests.every(test => test.flags.routers)),
  };
}
