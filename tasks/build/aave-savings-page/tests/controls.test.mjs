import test from 'node:test';
import assert from 'node:assert/strict';
import { chromium } from './deps.mjs';
import { prepareAction, submitAction, dismiss, visibleValues } from './controls.mjs';

test('drives an action section that has an input and button without an HTML form', async () => {
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage'] });
  try {
    const page = await browser.newPage();
    await page.setContent(`
      <section>
        <div><strong>USDC</strong><span>4.04%</span><button aria-label="Deposit USDC" onclick="choose('USDC')">Deposit</button></div>
        <div><strong>USDT</strong><span>3.43%</span><button aria-label="Deposit USDT" onclick="choose('USDT')">Deposit</button></div>
      </section>
      <section>
        <button role="tab">Deposit</button><button role="tab">Withdraw</button>
        <label>Asset<select onchange="choose(this.value)"><option>USDC</option><option>USDT</option></select></label>
        <div><label for="amount">Deposit amount</label><input id="amount" inputmode="decimal"><button>Max</button></div>
        <button id="submit" onclick="document.querySelector('output').innerText = selected + ' deposit: ' + document.querySelector('input').value">Deposit USDC</button>
      </section>
      <output></output>
      <script>let selected = 'USDC'; function choose(token) { selected = token; document.querySelector('#submit').innerText = 'Deposit ' + token; }</script>
    `);
    const action = await prepareAction(page, 'USDT', 'deposit', '100');
    await submitAction(action);
    assert.equal(await page.locator('output').innerText(), 'USDT deposit: 100');
    assert.equal(await page.locator('input').inputValue(), '100');
  } finally {
    await browser.close();
  }
});

test('drives the review counterexamples through their visible controls', async t => {
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
  try {
    for (const label of ['Supply', 'Supply USDC']) {
      await t.test(label, async () => {
        const page = await browser.newPage();
        await page.setContent(`<section><p>USDC</p><p>APY: 4.04%</p><p>100.33</p><small>Your balance</small>
          <input><button onclick="document.querySelector('output').innerText=document.querySelector('input').value">${label}</button><output></output></section>`);
        await submitAction(await prepareAction(page, 'USDC', 'deposit', '100'));
        assert.equal(await page.locator('output').innerText(), '100');
        assert.deepEqual((await visibleValues(page, 'USDC')).numbers, [100.33, 100]);
        await page.close();
      });
    }
    await t.test('ordinary mode buttons and a separate Confirm', async () => {
      const page = await browser.newPage();
      await page.setContent(`<section><p>USDC</p><p>APY: 4.04%</p>
        <button onclick="window.mode='deposit'">Deposit</button><button onclick="window.mode='withdraw'">Withdraw</button>
        <input><button onclick="document.querySelector('output').innerText=window.mode+':'+document.querySelector('input').value">Confirm</button><output></output></section>`);
      await submitAction(await prepareAction(page, 'USDC', 'withdraw', '40'));
      assert.equal(await page.locator('output').innerText(), 'withdraw:40');
      await page.close();
    });
    await t.test('two inputs and two Max buttons in one card', async () => {
      const page = await browser.newPage();
      await page.setContent(`<section><p>USDC</p><p>APY: 4.04%</p>
        <div><input id="deposit"><button onclick="document.querySelector('#deposit').value='999'">Max</button><button>Deposit</button></div>
        <div><input id="withdraw"><button onclick="document.querySelector('#withdraw').value='60.33'">Max</button>
        <button onclick="document.querySelector('output').innerText=document.querySelector('#deposit').value+'|'+document.querySelector('#withdraw').value">Withdraw</button></div><output></output></section>`);
      await submitAction(await prepareAction(page, 'USDC', 'withdraw', '40'));
      assert.equal(await page.locator('output').innerText(), '|40');
      await submitAction(await prepareAction(page, 'USDC', 'withdraw', '', true));
      assert.equal(await page.locator('output').innerText(), '|60.33');
      await page.close();
    });
    await t.test('token headers stay attached to their own action cards', async () => {
      const page = await browser.newPage();
      await page.setContent(['USDC', 'USDT'].map(token => `<div><div><h3>${token}</h3><span>4.04% APY</span></div>
        <div><input><button onclick="document.querySelector('output').innerText='${token}:'+this.previousElementSibling.value">Deposit</button></div></div>`).join('') + '<output></output>');
      await submitAction(await prepareAction(page, 'USDT', 'deposit', '100'));
      assert.equal(await page.locator('output').innerText(), 'USDT:100');
      await page.close();
    });
    await t.test('separate approval then supply', async () => {
      const page = await browser.newPage();
      await page.setContent(`<section><p>USDC</p><p>APY: 4.04%</p><input>
        <button onclick="if(this.innerText.startsWith('Approve'))this.innerText='Supply USDC';else document.querySelector('output').innerText='supplied '+document.querySelector('input').value">Approve USDC</button><output></output></section>`);
      await submitAction(await prepareAction(page, 'USDC', 'deposit', '100'), {
        complete: async () => (await page.locator('output').innerText()) === 'supplied 100',
      });
      assert.equal(await page.locator('output').innerText(), 'supplied 100');
      await page.close();
    });
    for (const review of [false, true]) {
      await t.test(review ? 'disabled review confirmation' : 'relabelled refusal', async () => {
        const page = await browser.newPage();
        await page.setContent(`<section><p>USDC</p><p>APY: 4.04%</p>
          <input oninput="${review ? '' : "document.querySelector('#submit').innerText='Exceeds supply cap'"}">
          <button id="submit" onclick="${review ? "document.querySelector('dialog').showModal()" : "document.querySelector('output').innerText='sent'"}">${review ? 'Review deposit' : 'Deposit'}</button>
          <output>no request</output></section><dialog><button disabled>Confirm deposit</button></dialog>`);
        assert.equal(await submitAction(await prepareAction(page, 'USDC', 'deposit', '6000', false, { allowRefusal: true })), false);
        assert.equal(await page.locator('output').innerText(), 'no request');
        await page.close();
      });
    }
  } finally { await browser.close(); }
});

test('reads visible balances and ties percentages to APY labels', async () => {
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
  try {
    const page = await browser.newPage();
    await page.setContent(`<section><h3>USDC</h3><p>APY: 0.00%</p><p>Benchmark rate: 4.04%</p>
      <span>Deposited</span><div>0 USDC</div><div hidden><span>Deposited</span><div>100.33 USDC</div></div>
      <form><input><button>Deposit</button></form></section>`);
    assert.deepEqual(await visibleValues(page, 'USDC'), {
      text: 'USDC\n\nAPY: 0.00%\n\nBenchmark rate: 4.04%\n\nDeposited\n0 USDC\nDeposit', percentages: [0], numbers: [0],
    });
    await page.locator('p').first().evaluate(node => { node.innerText = 'APY: 4.04%'; });
    await page.locator('section > div').first().evaluate(node => { node.innerText = '100.33 USDC'; });
    assert.deepEqual((await visibleValues(page, 'USDC')).percentages, [4.04]);
    assert.deepEqual((await visibleValues(page, 'USDC')).numbers, [100.33]);
    await page.locator('form').evaluate(node => node.remove());
    assert.deepEqual((await visibleValues(page, 'USDC')).percentages, [4.04]);
  } finally { await browser.close(); }
});

test('reviews and confirms a deposit instead of clicking the mode tab', async () => {
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage'] });
  try {
    const page = await browser.newPage();
    await page.setContent(`
      <button aria-label="Select USDC"><strong>USDC</strong><span>4.04%</span></button>
      <section>
        <button onclick="document.querySelector('input').value=''">Deposit</button><button>Withdraw</button>
        <form onsubmit="event.preventDefault(); document.querySelector('dialog').showModal()">
          <label>Amount<input inputmode="decimal" oninput="document.querySelector('#review').innerText=this.value ? 'Review deposit' : 'Enter an amount'"></label>
          <button id="review" type="submit">Enter an amount</button>
        </form>
      </section>
      <dialog><button disabled aria-label="Close dialog">Close</button><button onclick="document.querySelector('output').innerText='Confirmed USDC: '+document.querySelector('input').value; setTimeout(()=>document.querySelector('dialog').close(),50)">Confirm deposit</button></dialog>
      <output></output>
    `);
    await submitAction(await prepareAction(page, 'USDC', 'deposit', '100'));
    assert.equal(await page.locator('output').innerText(), 'Confirmed USDC: 100');
    await dismiss(page);
    assert.equal(await page.getByRole('dialog').isVisible(), false);
    await page.locator('body').evaluate(body => body.insertAdjacentHTML('beforeend', `
      <div>
        <div><span>Asset</span><span>Current APY</span><span>Balance incl. interest</span><span></span></div>
        <div><strong>USDC</strong><span>4.04%</span><div>98.765432 USDC</div><button aria-label="Deposit USDC">Deposit</button></div>
      </div>
    `));
    assert.deepEqual((await visibleValues(page, 'USDC')).numbers, [98.765432]);
  } finally {
    await browser.close();
  }
});
