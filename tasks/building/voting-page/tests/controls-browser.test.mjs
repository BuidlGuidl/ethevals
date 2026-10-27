import test from 'node:test';
import assert from 'node:assert/strict';
import { chromium } from './deps.mjs';
import { encodeFunctionData } from './deps.mjs';
import { governorAbi, votesAbi, executedCalls, voteRequests } from './chain.mjs';
import { forVoteMatches, proposalListVerdict } from './checks.mjs';
import { wrap, castVote, delegate, connect, openProposal, usableChoices, listedDescriptions, settled, emptyProposals } from './controls.mjs';

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
      const scope = await openProposal(session.page, 'Set the protocol fee');
      assert.equal(await scope.getAttribute('role'), 'dialog');
      await castVote(session, scope);
      assert.deepEqual(session.wallet.payloads, [{ support: 1 }]);
    });
    if (tag.startsWith('a ')) await fixture(`<a href="#vote" onclick="document.querySelector('dialog').showModal()">Set the protocol fee<br>Active<br>For 3M<br>Against 0</a>
      <dialog role="dialog"><button onclick="recordWrite({support:1})">For</button></dialog>`, async session => {
      const scope = await openProposal(session.page, 'Set the protocol fee');
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
test('voting follows a dialog that opens after the proposal click returns', async () => {
  const html = `<button onclick="setTimeout(()=>document.querySelector('[role=dialog]').hidden=false,400)">Funding vote</button>
    <div role="dialog" hidden><button onclick="recordWrite({support:1})">For</button></div>`;
  await fixture(html, async session => {
    const scope = await openProposal(session.page, 'Funding vote');
    await castVote(session, scope);
    assert.deepEqual(session.wallet.payloads, [{ support: 1 }]);
  });
  await fixture(html, async session => {
    const scope = await openProposal(session.page, 'Funding vote');
    await session.page.waitForTimeout(600);
    assert.deepEqual(await usableChoices(scope), ['For']);
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

test('listing waits for proposals to finish loading after connection', async () => {
  await fixture('<h1>Governance</h1><section></section><script>setTimeout(()=>document.querySelector("section").innerHTML="<article>#4 · Set the protocol fee<br>Active<br>For 12<br>Against 2</article>",1200)</script>', async ({ page }) => {
    assert.deepEqual(await listedDescriptions(page, ['Set the protocol fee']), ['Set the protocol fee']);
  });
});
test('opening a proposal waits for its title before driving its controls', async () => {
  await fixture(`<section></section><script>setTimeout(()=>document.querySelector('section').innerHTML='<article><h3>Funding vote</h3><button onclick="recordWrite({support:1})">Vote For</button></article>',700)</script>`, async session => {
    const scope = await openProposal(session.page, 'Funding vote');
    await castVote(session, scope);
    assert.deepEqual(voteRequests(session.wallet, GOVERNOR, 1n).map(call => call.args), [[1n, 1]]);
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
test('navigation waits for the wallet address to return', async () => {
  await fixture(`<p id="account">${HOLDER}</p><button onclick="document.querySelector('#account').innerText='Connecting';setTimeout(()=>document.querySelector('#account').innerText='${HOLDER}',400)">Governance</button>`, async ({ page }) => {
    assert.equal(await connect(page, HOLDER), true);
    assert.equal(await page.locator('#account').innerText(), HOLDER);
  });
});
test('For requesting support zero fails the For journey', async () => {
  await fixture('<button onclick="recordWrite({support:0})">Vote For</button>', async session => {
    await castVote(session, session.page);
    assert.equal(forVoteMatches(voteRequests(session.wallet, GOVERNOR, 1n), [{ support: 0, weight: 1000n }], 1000n), false);
    assert.equal(forVoteMatches([{ args: [1n, 1] }], [{ support: 1, weight: 1000n }], 1000n), true);
  });
});
test('settling waits for late controls and values', async () => {
  await fixture('<article>For 0<script>setTimeout(()=>document.querySelector("article").innerHTML="For 100<button>Vote Against</button>",400)</script></article>', async ({ page }) => {
    assert.equal((await settled(page.locator('article'))).trim(), 'For 100Vote Against');
    assert.deepEqual(await usableChoices(page.locator('article')), ['Against']);
  });
});
test('unsettled loading values produce a driver error', async () => {
  await fixture('<article>Loading votes</article>', async ({ page }) => {
    await assert.rejects(settled(page.locator('article'), { timeout: 400, quiet: 100 }), { message: 'could not drive: page values or controls did not settle' });
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
