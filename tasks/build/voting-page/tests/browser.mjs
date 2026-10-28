import fs from 'node:fs/promises';
import path from 'node:path';
import { createHarness } from './harness.mjs';
import { warmGovernance } from './warm.mjs';
import { CouldNotDrive } from './control-vocabulary.mjs';
import { connect, openProposal, castVote, wrap, delegate, dismiss, usableChoices,
  captureProposalList } from './controls.mjs';
import { UNIT, prepareFork, discoverAccounts, localAccounts, proposals, proposalState, governorAbi, votesAbi,
  value, mineTo, voteEvents, voteRequests, castRequests, executedCalls, createProposal } from './chain.mjs';
import { balance } from './rpc.mjs';
import { journey, forVoteMatches, proposalListVerdict } from './checks.mjs';

export const CHECKS = ['lists_every_proposal', 'status_and_tallies_match', 'quorum_counts_for_only',
  'end_moves_with_late_quorum', 'wrap_then_delegate', 'votes_at_snapshot', 'canceled_status', 'already_voted'];
const workspace = path.resolve(process.argv[2] || '/workspace');
const output = path.resolve(process.argv[3] || '/logs/verifier');
const sourceContext = process.argv[4] || '/chain/chain_context.json';
await fs.mkdir(output, { recursive: true, mode: 0o700 });
const stringify = data => JSON.stringify(data, (_, v) => typeof v === 'bigint' ? v.toString() : v, 2) + '\n';
const save = (name, data) => fs.writeFile(path.join(output, name), stringify(data));
let checks = {};
try { const previous = JSON.parse(await fs.readFile(path.join(output, 'checks.json'), 'utf8')); if (previous.compile) checks.compile = previous.compile; } catch {}
const evidence = { units: 'Governor tallies, quorum and holderVotes use whole tokens. Event weights use raw units with 18 decimals. End and snapshot are block numbers. States use OpenZeppelin Governor numbering.',
  texts: {}, checks: Object.fromEntries(CHECKS.slice(1, -1).map(name => [name, { captured: false, observations: [] }])) };
let proposalListEvidence = { titlesFound: [], governanceFound: false, governor: { count: 0, titles: [] }, listViews: [] };
const persist = async () => {
  await save('checks.json', checks);
  await save('page-evidence.txt', evidence);
  await save('proposal-list-evidence.txt', proposalListEvidence);
};
const record = async (name, passed, reason) => { checks[name] = { passed: Boolean(passed), reason }; await persist(); };
const check = async (name, run) => {
  await journey(checks, name, run, persist);
  if (checks[name]?.couldNotDrive) {
    if (evidence.checks[name]) Object.assign(evidence.checks[name], { captured: false, reason: checks[name].reason });
    if (harness?.active) await harness.capture(harness.active, name + '-could-not-drive').catch(() => {});
  } else if (evidence.checks[name]) evidence.checks[name].captured = true;
  await persist();
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
      prepare: async url => { fixture = await prepareFork(url, context, output); },
      warm: (url, wallet) => warmGovernance(url, context, wallet.address) });
    const { mainRpc: url, account } = harness;
    await save('fixture.json', { sourceBlock: harness.sourceBlock, wallet: account.address, proposals: fixture.proposals, checksBlock: fixture.checksBlock });
    async function session(wallet = account) {
      const s = await harness.session({ account: wallet });
      Object.assign(s, { governor: context.governor, voteToken: context.voteToken });
      s.governanceFound = await connect(s.page, wallet.address);
      return s;
    }
    async function reload(s) {
      await s.page.reload({ waitUntil: 'domcontentloaded' });
      await connect(s.page, account.address);
      await s.page.waitForTimeout(1800);
    }
    async function capture(s, label) {
      await s.page.waitForTimeout(1800);
      await harness.capture(s, label);
      const text = await s.page.locator('body').innerText();
      let id = Object.keys(evidence.texts).find(key => evidence.texts[key] === text);
      if (!id) { id = label; evidence.texts[id] = text; }
      return id;
    }
    async function observe(name, s, label, p, facts = {}) {
      const view = await capture(s, label);
      const chain = p ? await proposalState(url, context, p) : undefined;
      const truth = chain && { ...chain, for: String(chain.for / UNIT), against: String(chain.against / UNIT), quorum: String(chain.quorum / UNIT) };
      evidence.checks[name].observations.push({ label, description: p?.description, view, chain: truth, ...facts });
      await persist();
    }
    const selected = name => ({ ...fixture.proposals[name], id: BigInt(fixture.proposals[name].id) });
    const all = await proposals(url, context.governor);
    let s, absent = false;
    await check('lists_every_proposal', async () => {
      s = await session();
      proposalListEvidence = await captureProposalList(s, all.map(p => p.description), async () => {
        const view = await capture(s, 'list-' + Object.keys(evidence.texts).length);
        return evidence.texts[view];
      });
      await capture(s, 'initial');
      const listed = proposalListEvidence.titlesFound;
      absent = !listed.length && !proposalListEvidence.governanceFound;
      const result = proposalListVerdict({ shown: listed.length, total: all.length,
        governance: proposalListEvidence.governanceFound });
      if (result === 'could-not-drive') throw new CouldNotDrive('governance navigation showed no readable proposals');
      await record('lists_every_proposal', result === 'pass', `The fork has ${all.length} proposals; the page lists ${listed.length}. See initial-page.txt.`);
    });
    if (absent) {
      for (const name of CHECKS.slice(1)) {
        await record(name, false, 'The page has no governance control and shows no proposals.');
      }
    } else {
      await check('status_and_tallies_match', async () => {
        s = await session();
        for (const stage of ['before-original-end', 'after-original-end']) {
          for (const [index, p] of all.entries()) {
            await openProposal(s.page, p.description);
            await observe('status_and_tallies_match', s, `status-${stage}-${index}`, p);
          }
          if (stage === 'before-original-end') { await mineTo(url, selected('twin').originalDeadline + 2); await reload(s); }
        }
        await record('status_and_tallies_match', true, 'Captured status and tallies at both heights for the judge.');
      });
      await harness.reset();
      await check('quorum_counts_for_only', async () => {
        s = await session();
        for (const name of ['for_abstain', 'succeeded', 'extended']) {
          const p = selected(name); await openProposal(s.page, p.description);
          await observe('quorum_counts_for_only', s, 'quorum-' + name, p);
        }
        await record('quorum_counts_for_only', true, 'Captured For-only quorum for the judge.');
      });
      await harness.reset();
      await check('end_moves_with_late_quorum', async () => {
        s = await session();
        for (const name of ['extended', 'twin']) {
          const p = selected(name); await openProposal(s.page, p.description);
          await observe('end_moves_with_late_quorum', s, 'end-before-' + name, p);
        }
        await mineTo(url, selected('twin').originalDeadline + 2); await reload(s);
        for (const name of ['extended', 'twin']) {
          const p = selected(name); await openProposal(s.page, p.description);
          await observe('end_moves_with_late_quorum', s, 'end-after-' + name, p);
        }
        s = await session(localAccounts[1]);
        const p = selected('extended'), scope = await openProposal(s.page, p.description);
        await castVote(s, scope);
        await observe('end_moves_with_late_quorum', s, 'extended-voted', p);
        const events = voteEvents(s.wallet, context.governor, localAccounts[1].address, p.id), requests = voteRequests(s.wallet, context.governor, p.id);
        await save('extension.json', { events, requests });
        await record('end_moves_with_late_quorum', requests.length === castRequests(s.wallet).length && forVoteMatches(requests, events), 'Compared For request and VoteCast; the judge checks the ends and states.');
      });
      await harness.reset();
      let wrappedReady = false;
      await check('wrap_then_delegate', async () => {
        s = await session(); await wrap(s);
        const deposits = executedCalls(s.wallet, context.voteToken, votesAbi, 'depositFor');
        const combined = executedCalls(s.wallet, context.voteToken, votesAbi, 'delegate').some(call => call.args[0].toLowerCase() === account.address.toLowerCase());
        await dismiss(s.page); await reload(s);
        const wrapped = await balance(url, context.voteToken, account.address), afterWrap = await value(url, context.voteToken, votesAbi, 'getVotes', [account.address]);
        await observe('wrap_then_delegate', s, 'wrapped-undelegated', null, { combined, holderVotes: String(afterWrap / UNIT) });
        if (!combined) await delegate(s, account.address);
        await dismiss(s.page); await reload(s);
        const chainVotes = await value(url, context.voteToken, votesAbi, 'getVotes', [account.address]);
        await observe('wrap_then_delegate', s, 'delegated', null, { holderVotes: String(chainVotes / UNIT) });
        wrappedReady = chainVotes === 1000n * UNIT;
        await save('wrap-delegate.json', { wrapped, chainVotes, deposits, combined });
        await record('wrap_then_delegate', wrapped === 1000n * UNIT && deposits.some(call => call.args[0].toLowerCase() === account.address.toLowerCase() && call.args[1] === 1000n * UNIT)
          && executedCalls(s.wallet, context.voteToken, votesAbi, 'delegate').some(call => call.args[0].toLowerCase() === account.address.toLowerCase()) && wrappedReady,
        'Compared depositFor, delegation, balance and getVotes; the judge checks shown votes.');
      });
      await check('votes_at_snapshot', async () => {
        if (!wrappedReady) { await harness.reset(); s = await session(); await wrap(s); await delegate(s, account.address); await dismiss(s.page); await reload(s); }
        const old = selected('for_abstain'), scope = await openProposal(s.page, old.description);
        const oldChain = await value(url, context.governor, governorAbi, 'getVotes', [account.address, BigInt(old.snapshot)]);
        const current = await value(url, context.voteToken, votesAbi, 'getVotes', [account.address]);
        if (oldChain !== 0n) throw new Error('Old fixture weight is not zero');
        await observe('votes_at_snapshot', s, 'snapshot-old-before', old, { holderVotes: String(oldChain / UNIT), currentVotes: String(current / UNIT) });
        const choices = await usableChoices(scope);
        if (choices.length) {
          try { await castVote(s, scope, choices[0]); }
          catch (error) { if (!(error instanceof CouldNotDrive)) throw error; }
        }
        const requests = castRequests(s.wallet), events = voteEvents(s.wallet, context.governor, account.address, old.id);
        const oldPass = requests.length === voteRequests(s.wallet, context.governor, old.id).length
          && requests.every(call => call.args[0] === old.id && Number(call.args[1]) === ({ For: 1, Against: 0, Abstain: 2 }[choices[0]]))
          && events.every(event => event.weight === oldChain);
        if (!oldPass) await record('votes_at_snapshot', false, 'An old-proposal request or recorded weight differs from the chosen proposal and snapshot.');
        await observe('votes_at_snapshot', s, 'snapshot-old-after', old, { holderVotes: String(oldChain / UNIT), currentVotes: String(current / UNIT), voteRequestSent: requests.length > 0, events });
        await save('snapshot-old.json', { chain: oldChain, choices, requests, events });
        await dismiss(s.page);
        const fresh = await createProposal(url, context, fixture); await reload(s);
        const newScope = await openProposal(s.page, fresh.description), newWeight = await value(url, context.governor, governorAbi, 'getVotes', [account.address, fresh.voteStart]);
        await observe('votes_at_snapshot', s, 'snapshot-new-before', fresh, { holderVotes: String(newWeight / UNIT) });
        await castVote(s, newScope);
        const newEvents = voteEvents(s.wallet, context.governor, account.address, fresh.id), newRequests = voteRequests(s.wallet, context.governor, fresh.id);
        await observe('votes_at_snapshot', s, 'snapshot-new-after', fresh, { holderVotes: String(newWeight / UNIT), voteRequestSent: newRequests.length > 0, events: newEvents });
        await save('snapshot-new.json', { proposal: fresh, events: newEvents, requests: newRequests });
        const noOtherVotes = castRequests(s.wallet).length === requests.length + newRequests.length;
        await record('votes_at_snapshot', oldPass && noOtherVotes && newWeight === 1000n * UNIT && forVoteMatches(newRequests, newEvents, 1000n * UNIT), 'Compared proposal, support and snapshot weights; the judge checks shown weights.');
      });
      await harness.reset();
      for (const [name, p, wallet] of [['canceled_status', selected('canceled'), localAccounts[1]], ['already_voted', selected('for_abstain'), localAccounts[1]]]) {
        await check(name, async () => {
          s = await session(wallet);
          const hasVoted = await value(url, context.governor, governorAbi, 'hasVoted', [p.id, wallet.address]);
          if (name === 'already_voted' && !hasVoted) throw new Error('Already-voted fixture has no prior vote');
          const scope = await openProposal(s.page, p.description);
          if (name === 'canceled_status') await observe(name, s, name + '-before', p);
          else await capture(s, name + '-before');
          const choices = await usableChoices(scope);
          if (choices.length) {
            try { await castVote(s, scope, choices[0]); }
            catch (error) { if (!(error instanceof CouldNotDrive)) throw error; }
          }
          await capture(s, name + '-after');
          const requests = castRequests(s.wallet);
          await save(name + '.json', { proposal: p, hasVoted, choices, requests });
          await record(name, requests.length === 0, `The attempted vote sent ${requests.length} castVote requests. See ${name}.json.`);
        });
        await harness.reset();
      }
    }
  }
} catch (error) {
  await save('browser-error.json', { kind: 'trial-error', error: error.stack });
  console.error(error); process.exitCode = 1;
} finally {
  if (harness) await harness.close();
  await persist();
  await save('timing.json', { browserSeconds: (Date.now() - started) / 1000 });
}
