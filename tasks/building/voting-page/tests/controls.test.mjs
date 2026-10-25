import test from 'node:test';
import assert from 'node:assert/strict';
import { proposalValues, labelled, ambiguousWeight } from './controls.mjs';

test('reads proposal weight labels and tallies', () => {
  assert.deepEqual(proposalValues('Active\nFor\n2M\nAgainst\n500K\nQuorum 50%\n4M required\nVoting ends at Block 129,633'),
    { status: 1, for: 2000000, against: 500000, reached: false, quorum: 4000000, quorumProgress: null, end: 129633, endUnit: 'block', snapshot: null });
  assert.equal(proposalValues('Your votes\n1,000\nVote For').snapshot, 1000);
  assert.equal(proposalValues('Your snapshot votes: 0').snapshot, 0);
  assert.equal(proposalValues('Votes you will cast: 1,000').snapshot, 1000);
});
test('reads a For-only quorum refusal and moved end block', () => {
  assert.deepEqual(proposalValues('Succeeded\nFor: 3,000,000 · Against: 0 · Abstain: 2,000,000\nQuorum: 3,000,000 / 4,000,000 (75%) not reached\nVoting ends at block 215051'),
    { status: 4, for: 3000000, against: 0, reached: false, quorum: 4000000, quorumProgress: 3000000, end: 215051, endUnit: 'block', snapshot: null });
  assert.equal(proposalValues('You had no votes at block 79233, when this proposal\'s snapshot was taken.').snapshot, 0);
  assert.equal(labelled('For\n4.5M\nAgainst\n0', 'for'), 4500000);
});

test('reads ordinary quorum refusals', () => {
  for (const phrase of ['not yet reached', 'unmet', 'below quorum']) assert.equal(proposalValues(`Quorum ${phrase}`).reached, false);
  assert.equal(proposalValues('Quorum reached').reached, true);
});
test('takes the vote count after a percentage', () => {
  assert.equal(proposalValues('For 60% · 3,000,000').for, 3000000);
  assert.equal(proposalValues('For 60%').for, null);
});
test('status uses its label and excludes dated history', () => {
  assert.equal(proposalValues('Status: Executed\nPending\nActive\nQueued at block 15').status, 7);
  assert.equal(proposalValues('Executed\nQueued at block 15').status, 7);
});
test('an end label selects Ends rather than Starts', () => {
  assert.equal(proposalValues('Starts\nBlock 100\nEnds\nBlock 200').end, 200);
  assert.equal(proposalValues('Ends at block 250').end, 250);
  assert.deepEqual([proposalValues('Block 100').end, proposalValues('Ends in 2 days 3 hours').end], [null, 183600]);
  assert.equal(proposalValues('Voting ends November 1, 2026').endUnit, 'date');
  assert.deepEqual([proposalValues('20h 50m left\nBlock 215047').end, proposalValues('20h 50m left\nBlock 215047').endUnit], [75000, 'seconds']);
});
test('snapshot words do not confuse current votes', () => {
  for (const text of ['Voting power at snapshot: 0', 'Your voting power for this proposal: 0', 'You had 0 votes at the snapshot', 'Eligible votes: 0']) assert.equal(proposalValues(text).snapshot, 0);
  assert.equal(proposalValues('You have 1,000 votes (current)').snapshot, null);
});
test('an unlabelled timeline cannot select the current status', () => {
  assert.equal(proposalValues('Pending\nActive\nSucceeded\nQueued\nExecuted\nExecuted\nFor 12\nAgainst 2').status, null);
  assert.equal(proposalValues('Pending\nActive\nStatus: Executed\nFor 12\nAgainst 2').status, 7);
});
test('unnumbered zero-weight wording remains unresolved', () => {
  assert.equal(ambiguousWeight('You have no votes', null), true);
  assert.equal(ambiguousWeight('Snapshot block 208,700', null), false);
});
