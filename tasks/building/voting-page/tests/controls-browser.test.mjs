import test from 'node:test';
import assert from 'node:assert/strict';
import { chromium } from './deps.mjs';
import { encodeFunctionData } from './deps.mjs';
import { governorAbi, votesAbi, executedCalls, voteRequests } from './chain.mjs';
import { oldSnapshotVerdict, forVoteMatches, proposalListVerdict, statusAndTalliesMatch, journey, verdict } from './checks.mjs';
import { wrap, castVote, delegate, connect, proposal, proposalValues, votingScope, usableChoices, oldVoteView, currentVotes, findDescription, listedDescriptions, settled, ambiguousWeight, emptyProposals } from './controls.mjs';

const HOLDER = '0x0000000000000000000000000000000000000001';
const GOVERNOR = '0x0000000000000000000000000000000000000002';
const TOKEN = '0x0000000000000000000000000000000000000003';

async function fixture(html, run) {
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
  try {
    const page = await browser.newPage();
    const wallet = { payloads: [], requests: [], transactions: [], pending: 0, lastActivity: 0 };
    await page.exposeFunction('recordWrite', payload => {
      wallet.payloads.push(payload);
      const vote = 'support' in payload;
      const method = vote ? 'castVote' : payload.action === 'approve' ? 'delegate' : payload.action;
      const call = {to: vote ? GOVERNOR : TOKEN, data: encodeFunctionData({abi: vote ? governorAbi : votesAbi, functionName: method, args: vote ? [1n, payload.support] : method === 'depositFor' ? [HOLDER, 1000n] : [HOLDER]})};
      wallet.requests.push({ method: 'eth_sendTransaction', params: [call] });
      wallet.transactions.push({ payload });
      wallet.lastActivity = Date.now();
    });
    await page.setContent(html);
    await run({ page, wallet, governor: GOVERNOR, voteToken: TOKEN });
  } finally { await browser.close(); }
}

test('wrap submits the form below the amount instead of its mode tab', async () => {
  await fixture(`<div role="dialog">
    <button onclick="document.querySelector('input').value=''">Wrap TOKEN</button>
    <input aria-label="TOKEN amount">
    <button onclick="recordWrite({action:'depositFor',amount:document.querySelector('input').value})">wrap TOKEN</button>
    </div>`, async session => {
    await wrap(session);
    assert.deepEqual(session.wallet.payloads, [{ action: 'depositFor', amount: '1000' }]);
  });
});

test('wrap drives a separate approval and the wrap into vTOKEN label', async () => {
  await fixture(`<input placeholder="Amount of TOKEN"><button id="submit" onclick="submitWrap()">Approve TOKEN</button>
    <script>
    let approved = false;
    function submitWrap() {
      recordWrite({action:approved?'depositFor':'approve',amount:document.querySelector('input').value});
      approved = true;
      document.querySelector('#submit').innerText = 'Wrap into vTOKEN';
    }
    </script>`, async session => {
    await wrap(session);
    assert.deepEqual(session.wallet.payloads.map(payload => payload.action), ['approve', 'depositFor']);
    assert.equal(session.wallet.payloads[1].amount, '1000');
  });
});

test('wrap recognizes the combined approval control after entering an amount', async () => {
  await fixture(`<input oninput="document.querySelector('button').innerText='Approve & wrap';document.querySelector('button').disabled=false">
    <button disabled onclick="recordWrite({action:'depositFor',amount:document.querySelector('input').value})">Wrap</button>`, async session => {
    await wrap(session);
    assert.deepEqual(session.wallet.payloads, [{ action: 'depositFor', amount: '1000' }]);
  });
});

test('wrap waits for a delayed trigger before opening its amount dialog', async () => {
  await fixture(`<button id="open" disabled onclick="document.querySelector('dialog').showModal()">Wrap TOKEN</button>
    <dialog role="dialog"><input placeholder="0.00"><button onclick="recordWrite({action:'depositFor',amount:document.querySelector('input').value})">Wrap</button></dialog>
    <script>setTimeout(()=>document.querySelector('#open').disabled=false,400)</script>`, async session => {
    await wrap(session);
    assert.deepEqual(session.wallet.payloads, [{ action: 'depositFor', amount: '1000' }]);
  });
});

test('delegate waits for its delayed dialog trigger and submit', async () => {
  await fixture(`<button id="open" disabled onclick="document.querySelector('dialog').showModal();setTimeout(()=>document.querySelector('#submit').disabled=false,400)">Delegate</button>
    <dialog role="dialog"><input placeholder="Delegate address"><button id="submit" disabled onclick="recordWrite({action:'delegate',address:document.querySelector('input').value})">Delegate</button></dialog>
    <script>setTimeout(()=>document.querySelector('#open').disabled=false,400)</script>`, async session => {
    await delegate(session, HOLDER);
    assert.deepEqual(session.wallet.payloads, [{ action: 'delegate', address: HOLDER }]);
  });
});

test('self-delegation waits for a delayed direct control', async () => {
  await fixture(`<button disabled onclick="recordWrite({action:'delegate'})">Delegate to myself</button>
    <script>setTimeout(()=>document.querySelector('button').disabled=false,400)</script>`, async session => {
    await delegate(session, HOLDER);
    assert.deepEqual(session.wallet.payloads, [{ action: 'delegate' }]);
  });
});

test('completed direct delegation does not wait for a disabled submit', async () => {
  await fixture(`<button onclick="recordWrite({action:'delegate'});this.disabled=true">Delegate to yourself</button>
    <button disabled>Delegate</button>`, async session => {
    await delegate(session, HOLDER);
    assert.deepEqual(session.wallet.payloads, [{ action: 'delegate' }]);
  });
  await fixture(`<button onclick="recordWrite({action:'delegate'});document.querySelector('#self').hidden=false">Delegate</button>
    <button id="self" hidden disabled>Delegate to yourself</button>`, async session => {
    await delegate(session, HOLDER);
    assert.deepEqual(session.wallet.payloads, [{ action: 'delegate' }]);
  });
});

test('Delegate voting power opens delegation without clicking a status label', async () => {
  await fixture(`<button onclick="recordWrite({action:'wrong'})">Delegated to yourself</button>
    <button onclick="document.querySelector('dialog').showModal()">Delegate voting power</button>
    <dialog role="dialog"><input placeholder="Delegate address"><button onclick="recordWrite({action:'delegate',address:document.querySelector('input').value})">Delegate</button></dialog>`, async session => {
    await delegate(session, HOLDER);
    assert.deepEqual(session.wallet.payloads, [{ action: 'delegate', address: HOLDER }]);
  });
});

for (const tag of ['button', 'a href="#vote"', 'div role="button"']) {
  test(`a clickable ${tag} card opens its voting dialog`, async () => {
    await fixture(`<article><${tag} onclick="document.querySelector('dialog').showModal()">Set the protocol fee<br>Active<br>For 3M<br>Against 0</${tag.split(' ')[0]}></article>
      <dialog role="dialog"><p>1,000 snapshot votes</p><button onclick="recordWrite({support:1})">For</button></dialog>`, async session => {
      const scope = await votingScope(session.page, 'Set the protocol fee');
      assert.equal(await scope.getAttribute('role'), 'dialog');
      await castVote(session, scope);
      assert.deepEqual(session.wallet.payloads, [{ support: 1 }]);
    });
    if (tag.startsWith('a ')) await fixture(`<a href="#vote" onclick="document.querySelector('dialog').showModal()">Set the protocol fee<br>Active<br>For 3M<br>Against 0</a>
      <dialog role="dialog"><button onclick="recordWrite({support:1})">For</button></dialog>`, async session => {
      const scope = await votingScope(session.page, 'Set the protocol fee');
      assert.equal(await scope.getAttribute('role'), 'dialog');
      await castVote(session, scope);
      assert.deepEqual(session.wallet.payloads, [{ support: 1 }]);
    });
  });
}

test('Submit For vote drives the saved Codex dialog', async () => {
  await fixture(`<div role="dialog"><p>1,000 snapshot votes</p><button>For</button>
    <button onclick="recordWrite({support:1})">Submit For vote</button></div>`, async session => {
    const scope = session.page.getByRole('dialog');
    await castVote(session, scope);
    assert.deepEqual(session.wallet.payloads, [{ support: 1 }]);
  });
});

for (const wrong of [false, true]) {
  test(`button cards read their own values with ${wrong ? 'a wrong' : 'the right'} tally`, async () => {
    const descriptions = ['Set the protocol fee', 'Change the treasury allocation'];
    await fixture(`<div><button class="proposal-card">${descriptions[0]}<br>Active<br>For 3M<br>Against 0<br>Ends at block 200</button>
      <button class="proposal-card">${descriptions[1]}<br>Defeated<br>For ${wrong ? '4M' : '3M'}<br>Against 4.5M<br>Ends at block 100</button></div>`, async ({ page }) => {
      const checks = {}, values = [];
      await journey(checks, 'status_and_tallies_match', async () => {
        for (const [index, description] of descriptions.entries()) {
          const shown = proposalValues(await (await proposal(page, description, { descriptions })).innerText());
          values.push([shown.status, shown.for, shown.against, shown.end]);
          const passed = statusAndTalliesMatch(shown, { status: index ? 3 : 1, for: 3000000, against: index ? 4500000 : 0 });
          if (!passed) checks.status_and_tallies_match = { passed: false };
        }
        checks.status_and_tallies_match ||= { passed: true };
      }, async () => {});
      assert.deepEqual(values, [[1, 3000000, 0, 200], [3, wrong ? 4000000 : 3000000, 4500000, 100]]);
      assert.equal(verdict(checks), wrong ? 'fail' : 'pass');
    });
  });
}

test('a scope containing two proposal titles records could not drive', async () => {
  const descriptions = ['Set the protocol fee', 'Change the treasury allocation'];
  await fixture(`<div><h3>${descriptions[0]}</h3><h3>${descriptions[1]}</h3><p>Active<br>For 3M<br>Against 0</p></div>`, async ({ page }) => {
    const checks = {};
    await journey(checks, 'status_and_tallies_match', async () => {
      const shown = proposalValues(await (await proposal(page, descriptions[0], { descriptions })).innerText());
      checks.status_and_tallies_match = { passed: statusAndTalliesMatch(shown, { status: 1, for: 3000000, against: 0 }) };
    }, async () => {});
    assert.equal(verdict(checks), 'trial-error');
    assert.equal(checks.status_and_tallies_match.couldNotDrive, true);
    assert.match(checks.status_and_tallies_match.reason, /could not drive: proposal card.*contains another proposal/);
  });
});

// Text from the Opus r4 wrapped-undelegated holder panel.
const opusHolder = `Your votes
TOKEN balance
0
Wrapped (vTOKEN)
1,000
Delegated to
Nobody
Current votes
0

Your vTOKEN carries no votes until you delegate it. Delegate to yourself to vote directly.

Current votes include votes others have delegated to you. Each proposal counts the votes you had at its snapshot block, so wrap and delegate before a proposal's snapshot.`;

test('reads the saved Opus Current votes panel before and after delegation', async () => {
  await fixture(`<article>For 3M<br>Against 0</article><section>${opusHolder.replaceAll('\n', '<br>')}</section>`, async ({ page }) => {
    assert.equal(await currentVotes(page), 0);
    await page.locator('section').evaluate((el, text) => el.innerText = text, opusHolder.replace('Current votes\n0', 'Current votes\n1,000'));
    assert.equal(await currentVotes(page), 1000);
  });
});

test('wrong Opus Current votes after wrapping fails wrap_then_delegate', async () => {
  await fixture(`<section>${opusHolder.replace('Current votes\n0', 'Current votes\n1,000').replaceAll('\n', '<br>')}</section>`, async ({ page }) => {
    const afterWrap = await currentVotes(page);
    assert.equal(afterWrap, 1000);
    // The wrap journey allows zero or an unread value before delegation.
    assert.equal(afterWrap === null || afterWrap === 0, false);
  });
});

test('wrong Opus can-cast wording and a vote fail votes_at_snapshot at zero weight', async () => {
  await fixture(`<article>For 0<br>Against 0<br>You can cast 1,000 votes (your votes at the snapshot).
    <button onclick="recordWrite({support:1})">Vote For</button></article>`, async session => {
    const view = await oldVoteView(session.page.locator('article'));
    await castVote(session, session.page.locator('article'));
    assert.equal(view.shown, 1000);
    assert.equal(oldSnapshotVerdict({ shown: view.shown, current: 1000, usable: view.choices.length > 0,
      ambiguous: ambiguousWeight(view.text, view.shown), asked: voteRequests(session.wallet, GOVERNOR, 1n).length > 0 }), 'fail');
  });
});

test('voting submits once through either a direct For button or a vote form', async () => {
  await fixture('<button aria-label="Vote For" onclick="recordWrite({support:1});this.remove()">For</button>', async session => {
    await castVote(session, session.page);
    assert.deepEqual(session.wallet.payloads, [{ support: 1 }]);
  });
  await fixture('<button>For</button><button onclick="recordWrite({support:1})">Vote For</button>', async session => {
    await castVote(session, session.page);
    assert.deepEqual(session.wallet.payloads, [{ support: 1 }]);
  });
});

test('a prefixed title identifies its proposal card', async () => {
  await fixture('<article><h3>#4 · Set the protocol fee</h3><p>Active</p><p>For 12</p><p>Against 2</p></article>', async ({ page }) => {
    const card = await proposal(page, 'Set the protocol fee');
    assert.equal(proposalValues(await card.innerText()).for, 12);
    assert.equal(await findDescription(page, 'Set the protocol fee'), true);
  });
});
test('listing waits for proposals to finish loading after connection', async () => {
  await fixture('<h1>Governance</h1><section></section><script>setTimeout(()=>document.querySelector("section").innerHTML="<article>#4 · Set the protocol fee<br>Active<br>For 12<br>Against 2</article>",1200)</script>', async ({ page }) => {
    assert.deepEqual(await listedDescriptions(page, ['Set the protocol fee']), ['Set the protocol fee']);
  });
});
test('a vote confirmation modal reaches castVote', async () => {
  await fixture(`<button onclick="document.querySelector('dialog').showModal()">Vote For</button>
    <dialog role="dialog"><button onclick="recordWrite({support:1})">Confirm vote</button></dialog>`, async session => {
    assert.equal(await castVote(session, session.page), true);
    assert.deepEqual(voteRequests(session.wallet, GOVERNOR, 1n).map(call => call.args), [[1n, 1]]);
  });
});
test('a vote choice toggle followed by submit reaches castVote', async () => {
  await fixture('<button onclick="this.ariaPressed=true">For 60%</button><button onclick="recordWrite({support:1})">Cast vote</button>', async session => {
    assert.equal(await castVote(session, session.page), true);
    assert.deepEqual(voteRequests(session.wallet, GOVERNOR, 1n).map(call => call.args), [[1n, 1]]);
  });
});
test('activate voting power self-delegates', async () => {
  await fixture('<button onclick="recordWrite({action:\'delegate\'})">Activate voting power</button>', async session => {
    await delegate(session, HOLDER);
    assert.deepEqual(session.wallet.payloads, [{ action: 'delegate' }]);
  });
});
test('Governance tab button reaches proposals', async () => {
  await fixture(`<p>${HOLDER}</p><button role="tab" onclick="document.querySelector('article').hidden=false">Governance page</button>
    <article hidden>Set the protocol fee<br>Active<br>For 7<br>Against 1</article>`, async ({ page }) => {
    await connect(page, HOLDER);
    const card = await proposal(page, 'Set the protocol fee');
    assert.equal(proposalValues(await card.innerText()).for, 7);
  });
});
test('navigation waits for the wallet address to return', async () => {
  await fixture(`<p id="account">${HOLDER}</p><button onclick="document.querySelector('#account').innerText='Connecting';setTimeout(()=>document.querySelector('#account').innerText='${HOLDER}',400)">Governance</button>`, async ({ page }) => {
    assert.equal(await connect(page, HOLDER), true);
    assert.equal(await page.locator('#account').innerText(), HOLDER);
  });
});
test('zero snapshot wording accepts an enabled vote button', async () => {
  await fixture('<article>Voting power at snapshot: 0<button>Vote For</button></article>', async ({ page }) => {
    const scope = page.locator('article');
    const shown = proposalValues(await scope.innerText()).snapshot;
    assert.equal(oldSnapshotVerdict({ shown, current: 1000, usable: (await usableChoices(scope)).length > 0, asked: false }), 'pass');
  });
});
test('Against remains usable when For is disabled', async () => {
  await fixture('<article>Your snapshot votes: 1000<button disabled>Vote For</button><button onclick="recordWrite({support:0})">Vote Against</button></article>', async session => {
    const scope = session.page.locator('article');
    assert.deepEqual(await usableChoices(scope), ['Against']);
    await castVote(session, scope, 'Against');
    assert.equal(oldSnapshotVerdict({ shown: 1000, current: 1000, usable: true, asked: voteRequests(session.wallet, GOVERNOR, 1n).length > 0 }), 'fail');
  });
});
test('For requesting support zero fails the For journey', async () => {
  await fixture('<button onclick="recordWrite({support:0})">Vote For</button>', async session => {
    await castVote(session, session.page);
    assert.equal(forVoteMatches(voteRequests(session.wallet, GOVERNOR, 1n), [{ support: 0, weight: 1000n }], 1000n), false);
    assert.equal(forVoteMatches([{ args: [1n, 1] }], [{ support: 1, weight: 1000n }], 1000n), true);
  });
});
test('wallet panel accepts Voting power and a Votes line', async () => {
  await fixture('<section>Wrap TOKEN into vTOKEN voting weight</section><section><h2>Voting power</h2><p>Wrapped vTOKEN 1,000</p><p>Votes 0</p></section>', async ({ page }) => {
    assert.equal(await currentVotes(page), 0);
  });
});
test('the holder summary settles after reload despite an outside ticker', async () => {
  await fixture(`<aside>Loading news <span id="ticker">0</span></aside><section>Voting power<br>Wrapped vTOKEN 1,000<br>Your votes <span id="votes">0</span></section>
    <script>setTimeout(()=>document.querySelector('#votes').innerText='1,000',400);setInterval(()=>document.querySelector('#ticker').innerText=String(Date.now()),500)</script>`, async ({ page }) => {
    assert.equal(await currentVotes(page), 1000);
  });
});
test('settling waits for late controls and values', async () => {
  await fixture('<article>For 0<script>setTimeout(()=>document.querySelector("article").innerHTML="For 100<button>Vote Against</button>",400)</script></article>', async ({ page }) => {
    assert.equal((await settled(page.locator('article'))).trim(), 'For 100Vote Against');
    assert.deepEqual(await usableChoices(page.locator('article')), ['Against']);
  });
});
test('the old view waits for a late usable choice before accepting no controls', async () => {
  await fixture('<article>Your snapshot votes: 1000<button disabled>Vote For</button><script>setTimeout(()=>document.querySelector("article").insertAdjacentHTML("beforeend","<button>Vote Against</button>"),2500)</script></article>', async ({ page }) => {
    const view = await oldVoteView(page.locator('article'));
    assert.deepEqual({ shown: view.shown, choices: view.choices }, { shown: 1000, choices: ['Against'] });
  });
});
test('visits the Closed tab to find a proposal', async () => {
  await fixture('<button role="tab" onclick="document.querySelector(\'article\').hidden=false">Closed</button><article hidden>#4 · Set the protocol fee<br>Defeated<br>For 3<br>Against 4</article>', async ({ page }) => {
    assert.equal(await findDescription(page, 'Set the protocol fee'), true);
    assert.equal(proposalValues(await (await proposal(page, 'Set the protocol fee')).innerText()).status, 3);
  });
});
test('follows a proposal title link to its tallies', async () => {
  await fixture('<article><a href="#detail" onclick="document.querySelector(\'article\').innerHTML=\'Set the protocol fee<br>Status: Active<br>For 12<br>Against 2\'">#4 · Set the protocol fee</a></article>', async ({ page }) => {
    assert.equal(proposalValues(await (await proposal(page, 'Set the protocol fee')).innerText()).for, 12);
  });
});
test('opens details only when the card has no tallies', async () => {
  await fixture('<article>Set the protocol fee<button onclick="document.querySelector(\'dialog\').showModal()">View details</button></article><dialog role="dialog">Set the protocol fee<br>Status: Active<br>For 9<br>Against 2</dialog>', async ({ page }) => {
    assert.equal(proposalValues(await (await proposal(page, 'Set the protocol fee')).innerText()).for, 9);
  });
});
test('unsettled loading values produce a driver error', async () => {
  await fixture('<article>Loading votes</article>', async ({ page }) => {
    await assert.rejects(settled(page.locator('article'), { timeout: 400, quiet: 100 }), { message: 'could not drive: page values or controls did not settle' });
  });
});
for (const extra of ['Snapshot block 208,700', 'Your voting power: 1,000']) {
  test(`a zero-weight request fails with ${extra} on the old card`, async () => {
    await fixture(`<section>Your votes: 1,000</section><article>Set the protocol fee<br>Active<br>For 3M<br>Against 0<br>${extra}<button onclick="recordWrite({support:1})">Vote For</button></article>`, async session => {
      const scope = await proposal(session.page, 'Set the protocol fee');
      const { text, shown, choices } = await oldVoteView(scope);
      const ambiguous = ambiguousWeight(text, shown);
      await castVote(session, scope);
      assert.equal(oldSnapshotVerdict({ shown, current: 1000, usable: choices.length > 0, ambiguous, asked: voteRequests(session.wallet, GOVERNOR, 1n).length > 0 }), 'fail');
      assert.equal(ambiguous, false);
      assert.equal(shown, extra.startsWith('Snapshot') ? null : 1000);
    });
  });
}
for (const { name, text, shown, ambiguous, verdict } of [
  { name: 'old card with Total votes and no snapshot power', text: 'For 3,000,000\nAgainst 0\nTotal votes: 3,000,000\nYou had no voting power at the snapshot.', shown: 0, ambiguous: false, verdict: 'pass' },
  { name: 'old card with For votes and unnumbered eligibility', text: 'For votes 3,000,000\nAgainst 0\nNot eligible: you held no votes when voting opened', shown: null, ambiguous: true, verdict: 'could-not-drive' },
  { name: 'old card with current power and snapshot zero', text: 'For 3,000,000\nAgainst 0\nYour voting power: 1,000 · At snapshot: 0', shown: 0, ambiguous: false, verdict: 'pass' },
  { name: 'new card with Total votes before holder votes', text: 'For 0\nAgainst 0\nTotal votes: 0\nYou can vote with 1,000 votes', shown: 1000, ambiguous: false },
  { name: 'old card with votes after tallies and no holder wording', text: 'For 3,000,000 votes\nAgainst 0 votes', shown: null, ambiguous: false, verdict: 'fail' },
]) {
  test(`holder weight on ${name}`, async () => {
    await fixture(`<article><p>${text.replaceAll('\n', '<br>')}</p><button onclick="recordWrite({support:1})">Vote For</button></article>`, async session => {
      const scope = session.page.locator('article');
      const view = await oldVoteView(scope);
      const unresolved = ambiguousWeight(view.text, view.shown);
      await castVote(session, scope);
      assert.deepEqual(voteRequests(session.wallet, GOVERNOR, 1n).map(call => call.args), [[1n, 1]]);
      assert.equal(view.shown, shown);
      assert.equal(unresolved, ambiguous);
      if (verdict) assert.equal(oldSnapshotVerdict({ shown: view.shown, current: 1000, usable: view.choices.length > 0,
        ambiguous: unresolved, asked: voteRequests(session.wallet, GOVERNOR, 1n).length > 0 }), verdict);
    });
  });
}
test('an external proposal title with tallies reads without navigation', async () => {
  await fixture('<article><a href="https://explorer.example/proposal/1">Set the protocol fee</a><p>Status: Active</p><p>For 12</p><p>Against 2</p></article>', async ({ page }) => {
    const before = page.url();
    const text = await settled(await proposal(page, 'Set the protocol fee'));
    assert.deepEqual([proposalValues(text).for, proposalValues(text).against, page.url()], [12, 2, before]);
  });
});
test('a ticker and Loading outside the card do not block reading a closed proposal', async () => {
  await fixture(`<aside>Loading news <span id="ticker">0</span></aside><button role="tab" onclick="document.querySelector('article').hidden=false">Closed</button>
    <article hidden>Set the protocol fee<br>Defeated<br>For 3<br>Against 4</article>
    <script>setInterval(()=>document.querySelector('#ticker').innerText=String(Date.now()),500)</script>`, async ({ page }) => {
    const card = await proposal(page, 'Set the protocol fee');
    const shown = proposalValues(await settled(card));
    assert.deepEqual([shown.status, shown.for, shown.against], [3, 3, 4]);
  });
});
test('a settled empty Governance list is evidence of missing proposals', async () => {
  for (const message of ['No proposals', '0 proposals', 'Proposals: 0']) {
    await fixture(`<h1>Governance</h1><p>${message}</p>`, async ({ page }) => {
      const empty = await emptyProposals(page);
      const descriptions = await listedDescriptions(page, ['Set the protocol fee']);
      assert.equal(empty, true);
      assert.deepEqual(descriptions, []);
      assert.equal(proposalListVerdict({ shown: descriptions.length, total: 1, governance: true, empty }), 'fail');
      assert.equal(proposalListVerdict({ shown: 0, total: 1, governance: true, empty: false }), 'could-not-drive');
    });
  }
  await fixture('<article>Set the protocol fee<br>For 3<br>Against 4</article>', async ({ page }) => {
    assert.equal(await emptyProposals(page), false);
    assert.deepEqual(await listedDescriptions(page, ['Set the protocol fee']), ['Set the protocol fee']);
  });
});
