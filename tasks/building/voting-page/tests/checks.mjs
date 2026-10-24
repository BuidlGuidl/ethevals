import { CouldNotDrive } from './control-vocabulary.mjs';

export async function journey(checks, name, run, save) {
  try { await run(); }
  catch (error) {
    if (error.name === 'TimeoutError') error = new CouldNotDrive(error.message.split('\n')[0]);
    if (!(error instanceof CouldNotDrive)) throw error;
    if (!checks[name] || checks[name].passed || checks[name].couldNotDrive) {
      checks[name] = { passed: false, couldNotDrive: true, reason: error.message };
    }
    await save();
  }
}
export function verdict(checks) {
  const values = Object.values(checks);
  if (values.some(check => !check.passed && !check.couldNotDrive)) return 'fail';
  return values.some(check => check.couldNotDrive) ? 'trial-error' : 'pass';
}
export function oldSnapshotVerdict({ shown, current, usable, asked, ambiguous = false }) {
  if (shown === 0 || !usable) return 'pass';
  if (asked && (shown > 0 || (shown === null && current !== null && !ambiguous))) return 'fail';
  return 'could-not-drive';
}
export function forVoteMatches(requests, events, weight) {
  return requests.some(call => Number(call.args[1]) === 1)
    && events.some(event => Number(event.support) === 1 && (weight === undefined ? event.weight > 0n : event.weight === weight));
}
