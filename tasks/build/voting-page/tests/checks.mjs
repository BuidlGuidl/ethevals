import { CouldNotDrive } from './control-vocabulary.mjs';

export async function journey(checks, name, run, save) {
  try { await run(); }
  catch (error) {
    if (!checks[name] || checks[name].passed || checks[name].couldNotDrive) {
      checks[name] = { passed: false, couldNotDrive: true, reason: String(error?.message || error) };
    }
    await save();
  }
}
export function verdict(checks) {
  const values = Object.values(checks);
  if (values.some(check => !check.passed && !check.couldNotDrive)) return 'fail';
  return values.some(check => check.couldNotDrive) ? 'trial-error' : 'pass';
}
export function proposalListVerdict({ shown, total, governance, empty }) {
  if (!shown && governance && !empty) return 'could-not-drive';
  return shown === total ? 'pass' : 'fail';
}
export function oldSnapshotVerdict({ shown, current, usable, asked, ambiguous = false }) {
  if (shown === 0 || !usable) return 'pass';
  if (asked && (shown > 0 || (shown === null && current !== null && !ambiguous))) return 'fail';
  return 'could-not-drive';
}
export function quorumMatches(shown, chain) {
  if (shown.quorumProgress !== null && shown.quorumProgress !== chain.for) return false;
  if (shown.quorum !== null && shown.quorum !== chain.quorum) return false;
  if (shown.reached === null) throw new CouldNotDrive('quorum reached value');
  return shown.reached === (chain.for >= chain.quorum);
}
export function statusAndTalliesMatch(shown, chain) {
  const fields = ['status', 'for', 'against'];
  if (fields.some(key => shown[key] !== null && shown[key] !== chain[key])) return false;
  if (fields.some(key => shown[key] === null)) throw new CouldNotDrive('current status or tallies');
  return true;
}
export function endOrder(extended, twin) {
  if (extended.end === null || twin.end === null || extended.endUnit !== twin.endUnit || extended.end === twin.end) {
    throw new CouldNotDrive('distinct, comparable labelled voting ends for the twins');
  }
  return extended.end > twin.end;
}
export function forVoteMatches(requests, events, weight) {
  return requests.some(call => Number(call.args[1]) === 1)
    && events.some(event => Number(event.support) === 1 && (weight === undefined ? event.weight > 0n : event.weight === weight));
}
