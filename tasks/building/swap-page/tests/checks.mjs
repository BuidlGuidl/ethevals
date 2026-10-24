import { TOKENS } from './lib.mjs';

export const decimals = symbol => ['USDC', 'USDT'].includes(symbol) ? 6 : 18;
const abs = value => value < 0n ? -value : value;
const integer = value => typeof value === 'bigint' || typeof value === 'number' || (typeof value === 'string' && /^\d+$/.test(value));
export function walk(value) {
  if (!value || typeof value !== 'object') return [];
  return [value, ...Object.values(value).flatMap(child => Array.isArray(child) ? child.flatMap(walk) : walk(child))];
}
export function finiteDeadline(decoded) {
  const swaps = walk(decoded).filter(node => /^(?:exactInput|exactOutput|[V234]+_SWAP)/.test(node.function || node.command || node.action || ''));
  // An execute or multicall's inherited deadline governs its nested swaps.
  return swaps.length > 0 && swaps.every(node => {
    const bound = node.deadline ?? decoded.deadline;
    return integer(bound) && BigInt(bound) > 0n && BigInt(bound) < (1n << 64n) - 1n;
  });
}
export function sentMinimum(decoded, output) {
  const token = output === 'ETH' ? TOKENS.WETH : TOKENS[output];
  const matches = address => address?.toLowerCase() === token.toLowerCase()
    || (output === 'ETH' && address?.toLowerCase() === TOKENS.ETH.toLowerCase());
  const swapBounds = [];
  const settlementBounds = [];
  for (const node of walk(decoded)) {
    const last = node.hops?.at(-1)?.tokenOut || node.tokenOut || node.currencyOut
      || (node.poolKey ? node.poolKey[node.zeroForOne ? 'currency1' : 'currency0'] : null)
      || (Array.isArray(node.path) ? node.path.at(-1)?.intermediateCurrency : null);
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
    if (integer(node.amountOut) && (/^exactOutput/.test(name) || node.amountInMaximum !== undefined)) swapBounds.push(BigInt(node.amountOut));
  }
  const candidates = [...settlementBounds, ...(swapBounds.length ? [swapBounds.reduce((sum, value) => sum + value, 0n)] : [])];
  return candidates.length ? candidates.reduce((a, b) => a > b ? a : b) : null;
}
const numberPattern = '([0-9][0-9,]*(?:\\.[0-9]+)?)';
export function labelledAmount(text, label, symbol) {
  const expression = new RegExp(`(?:${label})[^\\n\\d]*(?:\\([^)]*\\))?[^\\n\\d]*[\\s\\n]*${numberPattern}\\s*${symbol}\\b`, 'ig');
  const results = [...text.matchAll(expression)].map(match => {
    const raw = match[1].replaceAll(',', '');
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
export function feeCheck(delta, input, output, success) {
  if (!success) return Object.values(delta.treasury).every(value => value === 0n) && Object.values(delta.user).every(value => value === 0n);
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
export function allowancesEmpty(state) {
  return state.erc20Allowances.every(item => item.amount === 0n)
    && state.permit2Allowances.every(item => item.amount === 0n || BigInt(item.expiration) <= state.timestamp);
}
export function routersEmpty(before, after) {
  return before.routerBalances.every((router, i) => Object.keys(TOKENS).every(symbol => after.routerBalances[i].balances[symbol] === router.balances[symbol]));
}
export function minimumCheck(display, decoded, output, received) {
  const sent = sentMinimum(decoded, output);
  if (!display.minimum || sent === null) return { passed: false, reason: 'could not read a minimum' };
  const shown = display.minimum.value;
  const receivedFloor = display.minimum.fallback ? shown * 99n / 100n : shown;
  return { passed: shown > 0n && sent * 100n >= shown * 99n && received >= receivedFloor,
    reason: `${display.minimum.fallback ? 'Derived' : 'Displayed'} minimum ${shown}; submitted minimum ${sent}; received ${received} base units of ${output}.` };
}
export function receivedCheck(text, output, received) {
  const display = labelledAmount(text, 'you\\s+(?:received|got)|(?:^|\\n)\\s*received|actual(?:ly)?(?: received| output)?', output);
  return { passed: Boolean(display && received > 0n && abs(display.value - received) <= display.tolerance),
    reason: `Received ${received} base units of ${output}; page amount ${display?.raw ?? 'could not read received amount'}.` };
}
