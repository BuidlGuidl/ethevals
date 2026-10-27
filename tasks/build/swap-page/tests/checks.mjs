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
export function sentMinimum(decoded, output) {
  const token = output === 'ETH' ? TOKENS.WETH : TOKENS[output];
  const matches = address => address?.toLowerCase() === token.toLowerCase()
    || (output === 'ETH' && address?.toLowerCase() === TOKENS.ETH.toLowerCase());
  const swapBounds = [];
  const settlementBounds = [];
  function enforced(value) {
    if (!value || typeof value !== 'object' || value.allowRevert) return [];
    return [value, ...Object.values(value).flatMap(child => Array.isArray(child) ? child.flatMap(enforced) : enforced(child))];
  }
  for (const node of enforced(decoded)) {
    const last = node.hops?.at(-1)?.tokenOut || node.tokenOut || node.currencyOut
      || (node.poolKey ? node.poolKey[node.zeroForOne ? 'currency1' : 'currency0'] : null)
      || (Array.isArray(node.path) ? (typeof node.path.at(-1) === 'string' ? node.path.at(-1) : node.path.at(-1)?.intermediateCurrency) : null);
    if (last && !matches(last)) continue;
    const settlementToken = node.token || node.currency;
    if (settlementToken && !matches(settlementToken)) continue;
    const name = node.function || node.command || node.action || '';
    if (/unwrap/i.test(name) && output !== 'ETH') continue;
    for (const key of ['amountOutMinimum', 'amountOutMin']) {
      if (integer(node[key])) swapBounds.push(BigInt(node[key]));
    }
    for (const key of ['amountMinimum', 'amountMin', 'minAmount']) {
      if (integer(node[key])) settlementBounds.push(BigInt(node[key]));
    }
    if (integer(node.amountOut) && (/^exactOutput|^swap\w*ForExact/.test(name) || node.amountInMaximum !== undefined)) swapBounds.push(BigInt(node.amountOut));
  }
  const candidates = [...settlementBounds, ...(swapBounds.length ? [swapBounds.reduce((sum, value) => sum + value, 0n)] : [])];
  return candidates.length ? candidates.reduce((a, b) => a > b ? a : b) : null;
}
const numberPattern = '([0-9][0-9,]*(?:\\.[0-9]+)?)';
export function labelledAmount(text, label, symbol) {
  const decoration = '[\\s\\p{S}\\p{P}]*';
  const expression = new RegExp(`(?:${label})${decoration}(?:${symbol}\\b${decoration}${numberPattern}|${numberPattern}\\s*${symbol}\\b)`, 'igu');
  const results = [...text.matchAll(expression)].map(match => {
    const raw = (match[1] || match[2]).replaceAll(',', '');
    const precision = (raw.split('.')[1] || '').length;
    const units = 10n ** BigInt(decimals(symbol));
    const [whole, fraction = ''] = raw.split('.');
    return { value: BigInt(whole) * units + BigInt((fraction + '0'.repeat(decimals(symbol))).slice(0, decimals(symbol))),
      tolerance: 10n ** BigInt(Math.max(0, decimals(symbol) - precision)), raw };
  });
  return results.at(-1) || null;
}
export function belief(text, output) {
  // Remove parenthesized percentage qualifiers before reading labelled amounts.
  const clean = text.replace(/\((?![^)]*\b(?:ETH|USDC|USDT)\b)[^)]*\)/g, '');
  let minimum = labelledAmount(clean, '\\bmin(?:imum)?(?: received)?|at least|worst[ -]case', output);
  const expected = labelledAmount(clean, '(?:you )?(?:receive(?!d)|get)(?: estimated)?|quote(?:d)?|expected(?: output)?', output);
  const slippage = /(?:slippage[^\d\n]*([0-9.]+)\s*%|([0-9.]+)\s*%\s*slippage)/i.exec(text);
  if (!minimum && expected && slippage) {
    const bips = BigInt(Math.round(Number(slippage[1] || slippage[2]) * 100));
    if (bips >= 0n && bips < 10000n) minimum = { ...expected, value: expected.value * (10000n - bips) / 10000n, fallback: true };
  }
  return { minimum, expected, slippage: slippage ? Number(slippage[1] || slippage[2]) : null };
}
export function deltas(before, after, transactions) {
  const gas = transactions.reduce((sum, tx) => sum + BigInt(tx.gasCost), 0n);
  return { gas,
    user: Object.fromEntries(Object.keys(TOKENS).map(symbol => [symbol, after.ownerBalances[symbol] - before.ownerBalances[symbol] + (symbol === 'ETH' ? gas : 0n)])),
    treasury: Object.fromEntries(Object.keys(TOKENS).map(symbol => [symbol, after.treasuryBalances[symbol] - before.treasuryBalances[symbol]])) };
}
export function confirmedBelief(previous, next) {
  return next?.minimum ? next : previous;
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
export function minimumCheck(display, decoded, output, received, reverted = false) {
  const sent = sentMinimum(decoded, output);
  if (!display.minimum || sent === null) return { passed: false, reason: 'could not read a minimum' };
  const shown = display.minimum.value;
  const receivedFloor = display.minimum.fallback ? shown * 99n / 100n : shown;
  return { passed: shown > 0n && sent * 100n >= shown * 99n && (reverted || received >= receivedFloor),
    reason: `${display.minimum.fallback ? 'Derived' : 'Displayed'} minimum ${shown}; submitted minimum ${sent}; received ${received} base units of ${output}.` };
}
export function receivedCheck(text, output, received) {
  const amountFirst = text.replace(new RegExp(`(${numberPattern}\\s*${output}|${output}\\s*${numberPattern})\\s+received\\b`, 'ig'), 'You received $1');
  const display = labelledAmount(amountFirst, 'you\\s+(?:received|got)|\\band\\s+received|(?:^|\\n)\\s*received|actual(?:ly)?(?: received| output)?|swapped[^\\n]*?\\bfor', output);
  return { passed: Boolean(display && received > 0n && abs(display.value - received) <= display.tolerance),
    reason: `Received ${received} base units of ${output}; page amount ${display?.raw ?? 'could not read received amount'}.` };
}

export function gradeJourney({ input, output, amount, mode, completed, before, after, baseline, transactions, display, pageText, marketResult, rejected }) {
  const delta = deltas(before, after, transactions);
  const swaps = transactions.filter(tx => tx.relevant);
  const successful = swaps.filter(tx => tx.receipt.status === '0x1' && hasSwapLog(tx.receipt));
  const success = successful.length > 0 && delta.user[output] > 0n && delta.user[input] < 0n;
  const swapTreasury = Object.fromEntries(Object.keys(TOKENS).map(symbol => [symbol,
    successful.reduce((sum, tx) => sum + (tx.treasuryDelta?.[symbol] ?? 0n), 0n)]));
  const cleanRevert = mode === 'moved' && swaps.length > 0 && swaps.every(tx => tx.receipt.status === '0x0')
    && feeCheck(delta, input, output, false);
  const minimum = (cleanRevert ? swaps : successful).map(tx => minimumCheck(display || {}, tx.decoded, output, delta.user[output], cleanRevert));
  const received = receivedCheck(pageText, output, delta.user[output]);
  const entered = enteredAmountCheck(amount, input, delta);
  return { success, delta, swapTreasury, entered, minimum, received,
    leftoverAllowances: {
      erc20: after.erc20Allowances.filter(item => item.amount !== 0n),
      permit2: after.permit2Allowances.filter(item => item.amount !== 0n && BigInt(item.expiration) > after.timestamp),
    },
    flags: {
      fee: completed && feeCheck(delta, input, output, success, swapTreasury)
        && (mode !== 'reject' || (rejected && !success)) && (mode !== 'race' || Boolean(marketResult && swaps.length)),
      minimum: (success || cleanRevert) && minimum.length > 0 && minimum.every(item => item.passed),
      approvals: success && allowancesEmpty(after),
      deadline: swaps.length > 0 && swaps.every(tx => finiteDeadline(tx.decoded, baseline.timestamp)),
      native: success && (output !== 'ETH' || (delta.user.ETH > 0n && delta.user.WETH === 0n)),
      routers: success && routersEmpty(baseline, after),
      received: success && received.passed,
    } };
}
