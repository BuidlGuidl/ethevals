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
