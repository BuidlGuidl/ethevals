import { walletWrites } from './rpc-policy.mjs';

export const CHECKS = ['deposit_usdc', 'withdraw_partial', 'withdraw_all', 'deposit_usdt_leftover_allowance', 'refuses_over_cap'];
const USDC_UNIT = 1_000_000n;
const near = (value, target, tolerance) => (value > target ? value - target : target - value) <= tolerance;
const usdc = value => {
  const sign = value < 0n ? '-' : '';
  const size = value < 0n ? -value : value;
  return `${sign}${size / USDC_UNIT}.${(size % USDC_UNIT).toString().padStart(6, '0')}`;
};

// A typed amount, as the judge entered it, in token units. Anything that is not a plain number is ignored.
export function typedUnits(value) {
  const text = String(value).replace(/[,\s_]/g, '');
  const match = /^(\d*)(?:\.(\d*))?$/.exec(text);
  if (!match || !(match[1] || match[2])) return null;
  return BigInt(match[1] || '0') * USDC_UNIT + BigInt((match[2] || '').slice(0, 6).padEnd(6, '0'));
}

// Each over-cap attempt lasts from typing an amount above the room until the next typing, or the session's end.
export function overCapAttempts({ conditions, typed, end }) {
  const caps = conditions.filter(condition => condition.kind === 'full-cap').sort((a, b) => a.time - b.time);
  const entries = [...typed].sort((a, b) => a.time - b.time);
  const attempts = [];
  entries.forEach((entry, index) => {
    const cap = caps.findLast(item => item.time <= entry.time);
    const units = typedUnits(entry.value);
    if (!cap || units === null || units <= BigInt(cap.room)) return;
    attempts.push({ value: entry.value, room: BigInt(cap.room), start: entry.time, end: entries[index + 1]?.time ?? end });
  });
  return attempts;
}

// moves: every transaction the page sent, mined, with the wallet's balances just before and after it.
export function gradeSavings({ compile, moves, requests, conditions, typed, end }) {
  if (!compile) {
    return Object.fromEntries(CHECKS.map(name => [name, { passed: false, reason: 'The project did not compile. See build.log and typecheck.log.' }]));
  }
  const mined = moves.filter(move => move.status === '0x1').map(move => ({ ...move,
    delta: Object.fromEntries(Object.keys(move.after).map(key => [key, BigInt(move.after[key]) - BigInt(move.before[key])])),
    before: Object.fromEntries(Object.entries(move.before).map(([key, value]) => [key, BigInt(value)])),
    after: Object.fromEntries(Object.entries(move.after).map(([key, value]) => [key, BigInt(value)])) }));
  const summary = list => list.map(move => `${move.hash.slice(0, 10)} USDC ${usdc(move.delta.usdc)} aUSDC ${usdc(move.delta.ausdc)} USDT ${usdc(move.delta.usdt)} aUSDT ${usdc(move.delta.ausdt)}`).join('; ') || 'none';
  const changes = `Page transactions mined: ${summary(mined)}.`;
  const checks = {};

  const deposit = mined.find(move => near(move.delta.ausdc, 100n * USDC_UNIT, 10_000n));
  checks.deposit_usdc = { passed: Boolean(deposit), reason: deposit
    ? `Transaction ${deposit.hash} added ${usdc(deposit.delta.ausdc)} aUSDC.`
    : `No page transaction added 100 aUSDC within 0.01 USDC. ${changes}` };

  const partial = mined.find(move => move.delta.usdc === 40n * USDC_UNIT && near(move.delta.ausdc, -40n * USDC_UNIT, 10_000n));
  checks.withdraw_partial = { passed: Boolean(partial), reason: partial
    ? `Transaction ${partial.hash} returned 40 USDC and removed ${usdc(-partial.delta.ausdc)} aUSDC.`
    : `No page transaction returned exactly 40 USDC while removing 40 aUSDC within 0.01 USDC. ${changes}` };

  // A position of at least 1 USDC, so closing leftover dust does not count.
  const closings = mined.filter(move => move.before.ausdc >= USDC_UNIT && move.delta.usdc > 0n && move.delta.ausdc < 0n
    && move.after.ausdc < USDC_UNIT);
  const closed = closings.find(move => move.after.ausdc === 0n && near(move.delta.usdc, move.before.ausdc, 2n));
  checks.withdraw_all = { passed: Boolean(closed), reason: closed
    ? `Transaction ${closed.hash} returned ${usdc(closed.delta.usdc)} USDC and left 0 aUSDC.`
    : `No page withdrawal of a USDC position closed it to exactly 0 aUSDC. Withdrawals that left less than 1 USDC: ${summary(closings)}.` };

  const seeds = conditions.filter(condition => condition.kind === 'old-usdt-approval');
  const usdt = mined.find(move => seeds.some(seed => move.block > seed.block) && near(move.delta.ausdt, 100n * USDC_UNIT, 10_000n));
  const seed = usdt && seeds.findLast(item => usdt.block > item.block);
  checks.deposit_usdt_leftover_allowance = { passed: Boolean(usdt), reason: !seeds.length
    ? 'The session never left a 1 USDT approval to the Pool.'
    : usdt ? `After a 1 USDT Pool approval at block ${seed.block}, transaction ${usdt.hash} added ${usdc(usdt.delta.ausdt)} aUSDT.`
      : `After a 1 USDT Pool approval, no page transaction added 100 aUSDT within 0.01 USDT. ${changes}` };

  const attempts = overCapAttempts({ conditions, typed, end });
  const asked = walletWrites(requests).filter(request => attempts.some(attempt => request.time >= attempt.start && request.time < attempt.end));
  const tried = attempts.map(attempt => `${attempt.value} USDC with ${usdc(attempt.room)} room`).join(', ');
  checks.refuses_over_cap = { passed: Boolean(deposit) && attempts.length > 0 && asked.length === 0, reason: !attempts.length
    ? 'No amount above the room left under the lowered supply cap was entered on the page.'
    : `Entered ${tried}; in-room deposit ${Boolean(deposit)}; wallet writes after entering it: ${asked.map(request => request.method).join(', ') || 'none'}.` };
  return checks;
}
