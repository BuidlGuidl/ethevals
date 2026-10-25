import fs from 'node:fs/promises';
import path from 'node:path';
import { createHarness } from './harness.mjs';
import { CouldNotDrive } from './control-vocabulary.mjs';
import { connect, proposal, proposalValues, currentVotes, votingScope, oldVoteView, castVote, wrap, delegate, dismiss,
  listedDescriptions, governanceControls, settled, ambiguousWeight, emptyProposals } from './controls.mjs';
import { UNIT, prepareFork, discoverAccounts, localAccounts, proposals, proposalState, governorAbi, votesAbi,
  value, mineTo, voteEvents, voteRequests, executedCalls, createProposal } from './chain.mjs';
import { balance } from './rpc.mjs';
import { journey, verdict, oldSnapshotVerdict, forVoteMatches, quorumMatches, endOrder, proposalListVerdict, statusAndTalliesMatch } from './checks.mjs';

export const CHECKS = ['lists_every_proposal', 'status_and_tallies_match', 'quorum_counts_for_only',
  'end_moves_with_late_quorum', 'wrap_then_delegate', 'votes_at_snapshot'];
const workspace = path.resolve(process.argv[2] || '/workspace');
const output = path.resolve(process.argv[3] || '/logs/verifier');
const sourceContext = process.argv[4] || '/chain/chain_context.json';
await fs.mkdir(output, { recursive: true, mode: 0o700 });
const stringify = data => JSON.stringify(data, (_, v) => typeof v === 'bigint' ? v.toString() : v, 2) + '\n';
const save = (name, data) => fs.writeFile(path.join(output, name), stringify(data));
let checks = {};
try { const previous = JSON.parse(await fs.readFile(path.join(output, 'checks.json'), 'utf8')); if (previous.compile) checks.compile = previous.compile; } catch {}
const persist = () => save('checks.json', checks);
const record = async (name, passed, reason) => { checks[name] = { passed: Boolean(passed), reason }; await persist(); };
const check = async (name, run) => {
  await journey(checks, name, run, persist);
  if (checks[name]?.couldNotDrive && harness?.active) {
    await harness.capture(harness.active, name + '-could-not-drive').catch(() => {});
    await save(name + '-page-errors.json', harness.active.errors);
  }
};
let harness, fixture;
const started = Date.now();
try {
  if (checks.compile?.passed === false) {
    for (const name of CHECKS) await record(name, false, 'The project did not compile.');
  } else {
    const context = JSON.parse(await fs.readFile(sourceContext, 'utf8'));
    await discoverAccounts(context.rpcUrl, context);
    harness = await createHarness({ workspace, output, sourceContext,
      funding: { nativeBalance: 10n * UNIT, transfers: [{ token: context.token, holder: localAccounts[0].address, amount: 1000n * UNIT }] },
      prepare: async url => { fixture = await prepareFork(url, context, output); } });
    const { mainRpc: url, account } = harness;
    await save('fixture.json', { sourceBlock: harness.sourceBlock, wallet: account.address, proposals: fixture.proposals, checksBlock: fixture.checksBlock });
    async function session(wallet = account) {
      const s = await harness.session({ account: wallet });
      Object.assign(s, { governor: context.governor, voteToken: context.voteToken });
      s.governanceFound = await connect(s.page, wallet.address);
      return s;
    }
    async function reload(s, wallet = account) {
      await s.page.reload({ waitUntil: 'domcontentloaded' });
      await connect(s.page, wallet.address);
    }
    async function readCard(s, description) {
      return proposalValues(await settled(await proposal(s.page, description)));
    }
    const selected = name => ({ ...fixture.proposals[name], id: BigInt(fixture.proposals[name].id) });
    const all = await proposals(url, context.governor);
    let s;
    const listed = [];
    let absent = false;
    let empty = false;
    await check('lists_every_proposal', async () => {
      s = await session();
      listed.push(...await listedDescriptions(s.page, all.map(p => p.description)));
      await harness.capture(s, 'initial');
      empty = !listed.length && await emptyProposals(s.page);
      const result = proposalListVerdict({ shown: listed.length, total: all.length,
        governance: s.governanceFound || await governanceControls(s.page).count() > 0, empty });
      if (result === 'could-not-drive') throw new CouldNotDrive('governance navigation showed no readable proposals');
      absent = !listed.length && !empty;
      await record('lists_every_proposal', result === 'pass',
        `The fork has ${all.length} proposals; the page lists ${listed.length}. See initial-page.txt.`);
    });
    if (absent) {
      for (const name of CHECKS.slice(1)) await record(name, false, 'The page has no governance control and shows no proposals.');
    } else if (empty) {
      for (const name of CHECKS.slice(1)) await check(name, async () => { throw new CouldNotDrive('the Governance page shows an empty proposal list'); });
    } else {
      await check('status_and_tallies_match', async () => {
        s = await session();
        const rows = [];
        for (const stage of ['before-original-end', 'after-original-end']) {
          for (const p of all) {
            const shown = await readCard(s, p.description);
            const chain = await proposalState(url, context, p);
            const passed = statusAndTalliesMatch(shown, { status: chain.state, for: Number(chain.for / UNIT), against: Number(chain.against / UNIT) });
            rows.push({ stage, description: p.description, shown, chain, passed });
            await save('status-comparisons.json', rows);
            if (!passed) await record('status_and_tallies_match', false, 'A visible status or tally differs from the chain. See status-comparisons.json.');
          }
          if (stage === 'before-original-end') { await mineTo(url, selected('twin').originalDeadline + 2); await reload(s); }
        }
        await record('status_and_tallies_match', rows.every(row => row.passed), 'Compared status and For/Against tallies at both heights. See status-comparisons.json.');
      });
      await harness.reset();
      await check('quorum_counts_for_only', async () => {
        s = await session();
        const rows = [];
        for (const name of ['for_abstain', 'succeeded', 'extended']) {
          const p = selected(name), shown = await readCard(s, p.description), chain = await proposalState(url, context, p);
          const passed = quorumMatches(shown, { for: Number(chain.for / UNIT), quorum: Number(chain.quorum / UNIT) });
          rows.push({ name, shown, chain, passed });
          await save('quorum-comparisons.json', rows);
          if (!passed) await record('quorum_counts_for_only', false, 'A visible quorum value differs from For-only quorum.');
        }
        await record('quorum_counts_for_only', rows.every(row => row.passed), 'Compared visible quorum with For-only quorum. See quorum-comparisons.json.');
      });
      await harness.reset();
      await check('end_moves_with_late_quorum', async () => {
        s = await session();
        const extended = selected('extended'), twin = selected('twin');
        const extendedBefore = await readCard(s, extended.description), twinBefore = await readCard(s, twin.description);
        const order = endOrder(extendedBefore, twinBefore);
        if (!order) await record('end_moves_with_late_quorum', false, 'The extended end does not follow its twin.');
        await mineTo(url, twin.originalDeadline + 2);
        await reload(s);
        const extendedAfter = await readCard(s, extended.description), twinAfter = await readCard(s, twin.description);
        if (extendedAfter.status === null || twinAfter.status === null) throw new CouldNotDrive('twins status after original end');
        const states = [2, 3, 4, 5, 6, 7].includes(twinAfter.status) && extendedAfter.status === 1;
        if (!states) await record('end_moves_with_late_quorum', false, 'The twins do not show closed and active states after the original end.');
        s = await session(localAccounts[1]);
        const scope = await votingScope(s.page, extended.description);
        await settled(scope);
        await castVote(s, scope);
        const events = voteEvents(s.wallet, context.governor, localAccounts[1].address, extended.id);
        const requests = voteRequests(s.wallet, context.governor, extended.id);
        await save('extension.json', { extendedBefore, twinBefore, extendedAfter, twinAfter, events, requests });
        await record('end_moves_with_late_quorum', order && states && forVoteMatches(requests, events), 'Compared end order, states, For request and VoteCast. See extension.json.');
      });
      await harness.reset();
      let wrappedReady = false;
      await check('wrap_then_delegate', async () => {
        s = await session();
        await wrap(s);
        const deposits = executedCalls(s.wallet, context.voteToken, votesAbi, 'depositFor');
        const combined = executedCalls(s.wallet, context.voteToken, votesAbi, 'delegate').some(call => call.args[0].toLowerCase() === account.address.toLowerCase());
        await dismiss(s.page); await reload(s);
        const afterWrap = await currentVotes(s.page), wrapped = await balance(url, context.voteToken, account.address);
        const intermediate = combined || afterWrap === null || afterWrap === 0;
        if (!intermediate) await record('wrap_then_delegate', false, 'The page shows nonzero votes after wrapping without delegation.');
        await harness.capture(s, 'wrapped-undelegated');
        if (!combined) await delegate(s, account.address);
        await dismiss(s.page); await reload(s);
        const afterDelegate = await currentVotes(s.page);
        const chainVotes = await value(url, context.voteToken, votesAbi, 'getVotes', [account.address]);
        wrappedReady = chainVotes === 1000n * UNIT;
        await save('wrap-delegate.json', { afterWrap, afterDelegate, wrapped, chainVotes, deposits, combined });
        if (afterDelegate === null) throw new CouldNotDrive('holder votes after delegation');
        await record('wrap_then_delegate', wrapped === 1000n * UNIT && deposits.length > 0 && intermediate
          && afterDelegate === 1000 && wrappedReady, 'Compared deposits, balance and displayed votes before and after delegation. See wrap-delegate.json.');
      });
      await check('votes_at_snapshot', async () => {
        if (!wrappedReady) { await harness.reset(); s = await session(); await wrap(s); await delegate(s, account.address); await dismiss(s.page); await reload(s); }
        const old = selected('for_abstain');
        const oldScope = await votingScope(s.page, old.description);
        const { text: oldText, shown: oldShown, choices } = await oldVoteView(oldScope);
        const ambiguous = ambiguousWeight(oldText, oldShown);
        const current = await currentVotes(s.page);
        const oldChain = await value(url, context.governor, governorAbi, 'getVotes', [account.address, BigInt(old.snapshot)]);
        if (oldChain !== 0n) throw new Error('Old fixture weight is not zero');
        let oldDriveError;
        if (choices.length && oldShown !== 0) {
          try { await castVote(s, oldScope, choices[0]); } catch (error) { if (!(error instanceof CouldNotDrive)) throw error; oldDriveError = error; }
        }
        const asked = voteRequests(s.wallet, context.governor, old.id).length > 0;
        const oldResult = oldSnapshotVerdict({ shown: oldShown, current, usable: choices.length > 0, asked, ambiguous });
        await save('snapshot-old.json', { shown: oldShown, currentShown: current, ambiguous, chain: oldChain, choices, asked, result: oldResult,
          events: voteEvents(s.wallet, context.governor, account.address, old.id) });
        if (oldResult === 'fail') await record('votes_at_snapshot', false, 'The old proposal shows nonzero or only current votes and asks for a vote despite zero snapshot weight.');
        await dismiss(s.page);
        const fresh = await createProposal(url, context, fixture);
        await reload(s);
        const newScope = await votingScope(s.page, fresh.description);
        const newShown = proposalValues(await settled(newScope)).snapshot;
        if (newShown === null) throw new CouldNotDrive('holder weight on the new proposal');
        await castVote(s, newScope);
        const events = voteEvents(s.wallet, context.governor, account.address, fresh.id), requests = voteRequests(s.wallet, context.governor, fresh.id);
        await save('snapshot-new.json', { proposal: fresh, shown: newShown, events, requests });
        const freshPass = newShown === 1000 && forVoteMatches(requests, events, 1000n * UNIT);
        if (!freshPass || oldResult === 'fail') await record('votes_at_snapshot', false, 'Snapshot weight, For request or VoteCast differs from the chain. See snapshot-old.json and snapshot-new.json.');
        else if (oldResult === 'could-not-drive') throw oldDriveError || new CouldNotDrive('ambiguous old-proposal weight');
        else await record('votes_at_snapshot', true, 'Old proposal has zero weight or no usable choice; new proposal casts its full weight For.');
      });
    }
  }
  if (verdict(checks) === 'trial-error') await save('trial-error.json', { reason: 'No check failed, but some checks could not be driven.' });
} catch (error) {
  await save('browser-error.json', { kind: 'trial-error', error: error.stack });
  console.error(error);
  process.exitCode = 1;
} finally {
  if (harness) await harness.close();
  await persist();
  await save('timing.json', { browserSeconds: (Date.now() - started) / 1000 });
}
