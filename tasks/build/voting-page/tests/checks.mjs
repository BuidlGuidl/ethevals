export async function journey(checks, name, run, save) {
  try { await run(); }
  catch (error) {
    if (!checks[name] || checks[name].passed || checks[name].couldNotDrive) {
      checks[name] = { passed: false, couldNotDrive: true, reason: String(error?.message || error) };
    }
    await save();
  }
}
export function proposalListVerdict({ shown, total, governance, empty }) {
  if (!shown && governance && !empty) return 'could-not-drive';
  return shown === total ? 'pass' : 'fail';
}
export function forVoteMatches(requests, events, weight) {
  return requests.some(call => Number(call.args[1]) === 1)
    && events.some(event => Number(event.support) === 1 && (weight === undefined ? event.weight > 0n : event.weight === weight));
}
