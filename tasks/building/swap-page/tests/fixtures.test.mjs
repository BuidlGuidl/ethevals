import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import { belief, confirmedBelief, gradeJourney } from './checks.mjs';

const root = process.env.SWAP_FIXTURE_OUTPUT;
const parse = text => JSON.parse(text, (_key, value) => typeof value === 'string' && /^-?\d+$/.test(value) ? BigInt(value) : value);
for (const [page, badFee] of [['opus-final', false], ['kimi-final', true], ['solution-picker', false]]) {
  test(`replays chain and browser evidence for ${page} through production grading`, { skip: !root }, async () => {
    const directory = path.join(root, page);
    const read = async name => parse(await fs.readFile(path.join(directory, name), 'utf8'));
    const baseline = await read('fixture.json');
    const journeys = await read('journeys.json');
    for (const result of journeys) {
      const { name, input, output, mode } = result;
      const presses = await read(`${name}-presses.json`);
      let display;
      for (const press of presses) {
        if (press.label !== 'wallet swap request') display = confirmedBelief(display, belief(press.text, output));
      }
      const wallet = await read(`${name}-wallet.json`);
      const grade = gradeJourney({ input, output, amount: String(result.amount), mode, completed: result.completed,
        before: await read(`${name}-before.json`), after: await read(`${name}-after.json`), baseline,
        transactions: await read(`${name}-transactions.json`), display,
        pageText: await fs.readFile(path.join(directory, `${name}-page.txt`), 'utf8'),
        marketResult: ['moved', 'race'].includes(mode),
        rejected: wallet.requests.some(request => request.error?.includes('rejected')) });
      assert.deepEqual(grade.flags, result.flags, `${name}: replay agrees with browser`);
      assert.equal(grade.entered, result.entered, `${name}: entered amount`);
      if (result.evidenceOnly || mode === 'moved') continue;
      assert.equal(grade.flags.fee, !badFee, `${name}: fee timing`);
      if (mode !== 'reject') assert.equal(grade.flags.deadline, !badFee, `${name}: deadline`);
      if (mode === 'normal') {
        assert.equal(grade.success, true, `${name}: swap`);
        assert.equal(grade.entered, true, `${name}: entered amount`);
        for (const flag of ['minimum', 'approvals', 'native', 'routers', 'received']) assert.equal(grade.flags[flag], true, `${name}: ${flag}`);
      }
    }
  });
}
