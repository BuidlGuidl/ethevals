import test from 'node:test';
import assert from 'node:assert/strict';
import { chromium } from './deps.mjs';
import { prepareSwap, pressThrough, nextAction } from './controls.mjs';
import { belief, confirmedBelief, minimumCheck } from './checks.mjs';

test('drives native selects through review and confirmation with the last visible belief', async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage();
    await page.setContent(`<section><div><input inputmode="decimal"><select><option>ETH</option><option>USDC</option><option>USDT</option></select></div>
      <select><option>USDC</option><option>ETH</option><option>USDT</option></select>
      <p>Minimum received 0.2 ETH</p><button aria-label="Swap direction" onclick="throw Error('Direction control is not a submit')">↓↑</button><button onclick="this.remove();document.querySelector('dialog').showModal()">Review swap</button></section>
      <dialog><p>Minimum received 0.19 ETH</p><button onclick="document.querySelector('output').textContent='sent'">Confirm swap</button></dialog><output></output>`);
    const action = await prepareSwap(page, 'USDC', 'ETH', '500');
    const wallet = { requests: [], pending: 0, lastActivity: 0 };
    const saved = [];
    await pressThrough(action, { wallet, isSwapRequest: () => false, maxPresses: 2, snapshot: async press => saved.push(press) });
    assert.deepEqual(await page.locator('select').evaluateAll(nodes => nodes.map(node => node.value)), ['USDC', 'ETH']);
    assert.equal(await page.locator('input').inputValue(), '500');
    assert.equal(await page.locator('output').innerText(), 'sent');
    assert.equal(saved.at(-1).belief.minimum.value, 190000000000000000n);
    assert.deepEqual(saved.map(press => press.label), ['Review swap', 'Confirm swap']);
  } finally { await browser.close(); }
});

for (const layout of ['empty output', 'logo buttons', 'logo only', 'descriptive labels']) {
  test(`selects and verifies the pair with ${layout}`, async () => {
    const browser = await chromium.launch({ headless: true });
    try {
      const page = await browser.newPage();
      const label = index => layout === 'descriptive labels' ? `aria-label="Select ${index ? 'output' : 'input'} token"` : '';
      const content = (symbol, index) => layout.startsWith('logo') ? `<img alt="${symbol} logo" src="data:,">${layout === 'logo only' ? '' : symbol}` : index && layout === 'empty output' ? 'Select token' : `${symbol} ▾`;
      await page.setContent(`<main><div><label>Sell<input id="amount"></label><button id="s0" ${label(0)} onclick="openPicker(0)">${content('ETH', 0)}</button></div>
        <div><label>Buy<input readonly></label><button id="s1" ${label(1)} onclick="openPicker(1)">${content('USDC', 1)}</button></div><button id="go">Swap</button>
        <dialog>${['ETH','USDC','USDT'].map(symbol => `<button onclick="pick('${symbol}')"><img alt="${symbol} logo" src="data:,">${symbol}</button>`).join('')}</dialog>
        <script>let slot;function openPicker(i){slot=i;document.querySelector('dialog').showModal()}
        function pick(s){document.getElementById('s'+slot).textContent=s+' ▾';document.querySelector('dialog').close()}</script></main>`);
      await prepareSwap(page, 'USDT', 'ETH', '1000');
      assert.match(await page.locator('#s0').innerText(), /USDT/);
      assert.match(await page.locator('#s1').innerText(), /ETH/);
      assert.equal(await page.locator('#amount').inputValue(), '1000');
      assert.equal(await (await nextAction(page)).getAttribute('id'), 'go');
    } finally { await browser.close(); }
  });
}

for (const layout of ['persistent refresh', 'switch flip', 'descriptive options']) {
  test(`presses Swap with ${layout}`, async () => {
    const browser = await chromium.launch({ headless: true });
    try {
      const page = await browser.newPage();
      const select = selected => `<select>${['ETH', 'USDC', 'USDT'].map(symbol => `<option ${symbol === selected ? 'selected' : ''}>${symbol}${layout === 'descriptive options' ? ' (token)' : ''}</option>`).join('')}</select>`;
      await page.setContent(`<main><div><input type="number">${select('ETH')}</div><button aria-label="Switch" onclick="throw Error('flip pressed')"><svg width="10" height="10"></svg></button>
        <div><input readonly>${select('USDC')}</div><p>Minimum received 0.19 ETH</p>
        ${layout === 'persistent refresh' ? '<button onclick="throw Error(\'refresh pressed\')">Refresh quote</button>' : ''}
        <div><div><div><button id="go" onclick="document.querySelector('output').textContent='sent'">Swap</button></div></div></div><output></output></main>`);
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      const action = await prepareSwap(page, 'USDC', 'ETH', '500');
      await pressThrough(action, { wallet: { requests: [], pending: 0, lastActivity: 0 }, isSwapRequest: () => false, maxPresses: 1, snapshot: async () => {} });
      assert.equal(await page.locator('output').innerText(), 'sent');
      assert.deepEqual(errors, []);
    } finally { await browser.close(); }
  });
}

for (const pending of ['Confirm in your wallet', 'Minimum received 0.01 ETH']) {
  test(`keeps the confirmed minimum when the page changes to ${pending}`, async () => {
    const browser = await chromium.launch({ headless: true });
    try {
      const page = await browser.newPage();
      await page.setContent(`<main><input><select><option>USDC</option></select><select><option>ETH</option></select>
        <p>Minimum received 0.2 ETH</p><button onclick="document.querySelector('main').textContent='${pending}'">Confirm swap</button></main>`);
      const action = await prepareSwap(page, 'USDC', 'ETH', '500');
      let display;
      await pressThrough(action, { wallet: { requests: [], pending: 0, lastActivity: 0 }, isSwapRequest: () => false, maxPresses: 1,
        snapshot: async press => { display = confirmedBelief(display, press.belief); } });
      assert.equal(display.minimum.value, 200000000000000000n);
      const walletView = belief(await page.locator('body').innerText(), 'ETH');
      assert.equal(minimumCheck(display, { amountOutMinimum: 10000000000000000n }, 'ETH', 210000000000000000n).passed, false);
      assert.equal(minimumCheck(display, { amountOutMinimum: 200000000000000000n }, 'ETH', 210000000000000000n).passed, true);
      if (!walletView.minimum) assert.equal(confirmedBelief(display, walletView), display);
    } finally { await browser.close(); }
  });
}

test('uses input and output labels when the output slot appears first', async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage();
    await page.setContent(`<main><div><input id="out"><button aria-label="Select output token">ETH</button></div>
      <div><input id="in"><button aria-label="Select input token">USDC</button></div><button>Swap</button></main>`);
    await prepareSwap(page, 'USDC', 'ETH', '500');
    assert.equal(await page.locator('#in').inputValue(), '500');
    assert.equal(await page.locator('#out').inputValue(), '');
  } finally { await browser.close(); }
});

test('drives a token picker dialog and a one-button form without prescribing widget names', async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage();
    await page.setContent(`<section><input><button id="from" onclick="window.slot='from';document.querySelector('dialog').showModal()">ETH</button>
      <button id="to" onclick="window.slot='to';document.querySelector('dialog').showModal()">USDC</button>
      <button onclick="document.querySelector('output').textContent=document.querySelector('input').value">Swap</button><output></output></section>
      <dialog>${['ETH','USDC','USDT'].map(token => `<button onclick="document.getElementById(window.slot).textContent='${token}';document.querySelector('dialog').close()">${token}</button>`).join('')}</dialog>`);
    const action = await prepareSwap(page, 'USDT', 'ETH', '1000');
    await pressThrough(action, { wallet: { requests: [], pending: 0, lastActivity: 0 }, isSwapRequest: () => false, maxPresses: 1, snapshot: async () => {} });
    assert.equal(await page.locator('#from').innerText(), 'USDT');
    assert.equal(await page.locator('#to').innerText(), 'ETH');
    assert.equal(await page.locator('output').innerText(), '1000');
  } finally { await browser.close(); }
});
