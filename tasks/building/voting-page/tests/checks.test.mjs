import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import { journey, verdict, oldSnapshotVerdict, forVoteMatches } from './checks.mjs';
import { CouldNotDrive } from './control-vocabulary.mjs';
import { executedCalls, votesAbi, voteRequests, governorAbi } from './chain.mjs';
import { encodeFunctionData } from './deps.mjs';

test('a known fail survives an unresolved flow and other checks continue', async () => {
  const checks = {};
  await journey(checks, 'old', async () => { checks.old = { passed: false, reason: 'Wrong old weight' }; throw new CouldNotDrive('new proposal'); }, async () => {});
  await journey(checks, 'wrap', async () => { throw new CouldNotDrive('wrap'); }, async () => {});
  await journey(checks, 'quorum', async () => { checks.quorum = { passed: true, reason: 'For only' }; }, async () => {});
  assert.deepEqual(checks, { old: { passed: false, reason: 'Wrong old weight' }, wrap: { passed: false, couldNotDrive: true, reason: 'could not drive: wrap' }, quorum: { passed: true, reason: 'For only' } });
  assert.equal(verdict(checks), 'fail');
  assert.equal(verdict({ wrap: checks.wrap, quorum: checks.quorum }), 'trial-error');
  assert.equal(verdict({ quorum: checks.quorum }), 'pass');
});
test('ambiguous old weight needs a request and an actual shown number to fail', () => {
  assert.equal(oldSnapshotVerdict({ shown: null, current: null, usable: true, asked: true }), 'could-not-drive');
  assert.equal(oldSnapshotVerdict({ shown: null, current: 1000, usable: true, asked: true }), 'fail');
  assert.equal(oldSnapshotVerdict({ shown: 1000, current: 1000, usable: true, asked: false }), 'could-not-drive');
  assert.equal(oldSnapshotVerdict({ shown: null, current: 1000, usable: true, asked: true, ambiguous: true }), 'could-not-drive');
});
test('For requires support one in both request and event', () => {
  assert.equal(forVoteMatches([{ args: [1n, 0] }], [{ support: 1, weight: 1000n }]), false);
  assert.equal(forVoteMatches([{ args: [1n, 1] }], [{ support: 0, weight: 1000n }]), false);
  assert.equal(forVoteMatches([{ args: [1n, 1] }], [{ support: 1, weight: 1000n }]), true);
});
test('a bundled deposit uses the executed call rather than the bundle envelope', () => {
  const to = '0x0000000000000000000000000000000000000001';
  const call = { to, data: encodeFunctionData({ abi: votesAbi, functionName: 'depositFor', args: [to, 1000n] }) };
  const wallet = { transactions: [{ call, hash: '0x1234', request: { method: 'wallet_sendCalls', params: [{ calls: [call] }] }, receipt: { status: '0x1' } }] };
  assert.deepEqual(executedCalls(wallet, to, votesAbi, 'depositFor'), [{ hash: '0x1234', functionName: 'depositFor', args: [to, 1000n] }]);
  const individual = { transactions: [{ ...wallet.transactions[0], call: { to, input: call.data } }] };
  assert.deepEqual(executedCalls(individual, to, votesAbi, 'depositFor'), [{ hash: '0x1234', functionName: 'depositFor', args: [to, 1000n] }]);
});
test('bundled vote requests decode proposal and support', () => {
  const to = '0x0000000000000000000000000000000000000001';
  const call = { to, data: encodeFunctionData({ abi: governorAbi, functionName: 'castVote', args: [9n, 1] }) };
  assert.deepEqual(voteRequests({ requests: [{ method: 'wallet_sendCalls', params: [{ calls: [call] }] }] }, to, 9n), [{ functionName: 'castVote', args: [9n, 1] }]);
});
test('the verifier and setup use the same seed logic', async () => {
  assert.equal(await fs.readFile(new URL('./seed.py', import.meta.url), 'utf8'), await fs.readFile(new URL('../environment/setup/seed.py', import.meta.url), 'utf8'));
});
