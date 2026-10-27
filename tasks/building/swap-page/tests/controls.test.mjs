import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import { chromium } from './deps.mjs';
import { connect, prepareSwap, pressThrough, nextAction, waitForQuote, openDetails, actionKind } from './controls.mjs';
import { belief, confirmedBelief, minimumCheck } from './checks.mjs';

test('classifies action labels and rejects direction and token-picker labels', () => {
  for (const [label, expected] of [
    ['Swap tokens', 'swap'], ['Get quote', 'quote'], ['Sign', 'permission'],
    ['Permit', 'permission'], ['Submit', 'swap'], ['Allow USDC', 'permission'],
    ['Enable USDC', 'permission'], ['Refresh quote', 'refresh'], ['Switch to Ethereum', 'swap'],
    ['Swap tokens direction', null], ['↕', null], ['Select token', null],
    ['Choose output token', null], ['USDC', null], ['Switch tokens', null], ['Switch', null],
  ]) assert.equal(actionKind(label), expected, label);
});

test('presses general actions near the form and ignores navigation, pickers, and flips', async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage();
    for (const label of ['Swap tokens', 'Get quote', 'Sign', 'Permit', 'Submit', 'Allow USDC', 'Enable USDC']) {
      await page.setContent(`<nav><button>Submit</button></nav><main><input>
        <button>Swap tokens direction</button><button>↕</button>
        <button aria-haspopup="listbox">Swap tokens</button><button>Select token</button>
        <button>USDC</button><button id="action">${label}</button></main>`);
      assert.equal(await (await nextAction(page)).getAttribute('id'), 'action', label);
      await (await nextAction(page)).click();
      assert.equal(await (await nextAction(page)).innerText(), label);
    }
  } finally { await browser.close(); }
});

test('dismisses differently worded stale quotes and keeps the six-press limit', async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage();
    await page.setContent(`<main><input><button onclick="window.count=(window.count||0)+1">Submit</button></main>
      <dialog open><p>This price is no longer valid. Request a fresh rate.</p>
      <button onclick="this.closest('dialog').close()">Dismiss</button><button disabled>Submit</button></dialog>`);
    const presses = [];
    await pressThrough({ page, output: 'ETH' }, { wallet: { requests: [], pending: 0, lastActivity: 0 },
      isSwapRequest: () => false, snapshot: async press => presses.push(press.label) });
    assert.deepEqual(presses, ['Dismiss', 'Submit', 'Submit', 'Submit', 'Submit', 'Submit']);
    assert.equal(await page.evaluate(() => window.count), 5);
  } finally { await browser.close(); }
});

test('waits for a delayed quote and opens Review before the market move despite icon buttons', async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage();
    await page.setContent(`<main><input><button aria-label="Swap"><svg></svg></button>
      <p id="quote">Finding your quote…</p><button id="review" disabled onclick="document.querySelector('dialog').showModal()">Review swap</button></main>
      <dialog><p>Minimum received 0.19 ETH</p><button>Confirm swap</button></dialog>`);
    assert.equal(await nextAction(page), null);
    await page.evaluate(() => {
      const app = document.createElement('div');
      app.append(...document.body.childNodes);
      const nav = document.createElement('nav');
      nav.innerHTML = '<button>Swap</button>';
      app.prepend(nav);
      document.body.append(app);
    });
    assert.equal(await nextAction(page), null);
    await assert.rejects(waitForQuote(page, 'ETH', 200), /swap quote or named confirmation action/);
    await page.evaluate(() => setTimeout(() => {
      document.getElementById('quote').textContent = 'Expected output: 0.2 ETH';
      document.getElementById('review').disabled = false;
    }, 500));
    await waitForQuote(page, 'ETH');
    await (await nextAction(page)).click();
    assert.equal(await page.getByRole('dialog').isVisible(), true);
    assert.match(await page.getByRole('dialog').innerText(), /Confirm swap/);
    await page.setContent('<p>Expected output: 12 USDC</p>');
    await waitForQuote(page, 'USDC', 200);
    await page.setContent('<main><input><button>Swap</button></main>');
    await waitForQuote(page, 'ETH', 200);
  } finally { await browser.close(); }
});

test('opens a minimum disclosure once without pressing a committing control', async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage();
    for (const label of ['Details', 'More', 'Show', 'Show more', 'Show details']) {
      await page.setContent(`<dialog open><button aria-expanded="false" onclick="this.setAttribute('aria-expanded',this.getAttribute('aria-expanded')!=='true');document.querySelector('p').hidden=!document.querySelector('p').hidden">${label}</button>
        <p hidden>Minimum received 0.2 ETH</p><button onclick="window.committed=true">Confirm swap</button></dialog>`);
      const action = { page };
      await openDetails(action);
      await openDetails(action);
      assert.equal(belief(await page.locator('body').innerText(), 'ETH').minimum.value, 200000000000000000n, label);
      assert.equal(await page.evaluate(() => window.committed), undefined);
    }
    await page.setContent('<button>Show and confirm swap</button>');
    const action = { page };
    await openDetails(action);
    assert.equal(action.detailsOpened, undefined);
    await page.setContent('<details><summary>Show more</summary><p>Minimum received 0.2 ETH</p></details>');
    await openDetails({ page });
    await openDetails({ page });
    assert.equal(belief(await page.locator('body').innerText(), 'ETH').minimum.value, 200000000000000000n);
  } finally { await browser.close(); }
});

test('closes an expired review only when the page asks for that step to refresh', async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage();
    await page.setContent(`<div><nav><button onclick="throw Error('Navigation is not a swap action')">Swap</button></nav>
      <main><input><button id="review" disabled onclick="document.querySelector('dialog').showModal();document.querySelector('#confirm').disabled=false;document.querySelector('#confirm').textContent='Confirm swap'">Review swap</button>
        <button aria-label="Refresh quote" onclick="document.querySelector('#review').disabled=false"><svg></svg></button></main>
      <dialog open><button aria-label="Close swap preview" onclick="document.querySelector('dialog').close()"><svg></svg></button>
        <p>Minimum received 0.2 ETH</p><button id="confirm" disabled onclick="document.querySelector('output').textContent='sent'">Quote expired · close to refresh</button></dialog><output></output></div>`);
    const saved = [];
    await pressThrough({ page, output: 'ETH' }, { wallet: { requests: [], pending: 0, lastActivity: 0 }, isSwapRequest: () => false,
      maxPresses: 4, snapshot: async press => saved.push(press) });
    assert.deepEqual(saved.map(press => press.label), ['Close swap preview', 'Refresh quote', 'Review swap', 'Confirm swap']);
    assert.equal(await page.locator('output').innerText(), 'sent');
    await page.setContent('<dialog open><button aria-label="Close swap preview"><svg></svg></button><button disabled>Confirm swap</button></dialog>');
    assert.equal(await nextAction(page), null);
  } finally { await browser.close(); }
});

test('drives the GLM TokenRow radio layout with full token names and disabled opposite choices', async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage();
    await page.setContent(await fs.readFile(new URL('./fixtures/token-rows.html', import.meta.url), 'utf8'));
    for (const [input, output] of [['USDC', 'ETH'], ['ETH', 'USDC'], ['USDT', 'USDC']]) {
      await prepareSwap(page, input, output, '500');
      assert.deepEqual(await page.locator('[aria-checked="true"]').evaluateAll(nodes => nodes.map(node => node.dataset.symbol)), [input, output]);
      assert.equal(await page.locator('input').inputValue(), '500');
    }
  } finally { await browser.close(); }
});

for (const layout of ['select', 'button', 'option']) for (const tether of ['Tether USD', 'Tether']) {
  test(`accepts full token names and ${tether} in ${layout} controls`, async () => {
    const browser = await chromium.launch({ headless: true });
    try {
      const page = await browser.newPage();
      const names = ['Ether', 'USD Coin', tether];
      const choices = names.map((name, i) => `<option value="${i}">${name}</option>`).join('');
      await page.setContent(`<main><div><input>${layout === 'select' ? `<select id="s0">${choices}</select>` : '<button id="s0" onclick="openPicker(0)">Ether</button>'}</div>
        <div><output></output>${layout === 'select' ? `<select id="s1">${choices}</select>` : '<button id="s1" onclick="openPicker(1)">USD Coin</button>'}</div><button>Swap</button>
        <dialog>${names.map(name => `<button ${layout === 'option' ? 'role="option"' : ''} onclick="pick('${name}')">${name}</button>`).join('')}</dialog>
        <script>let slot;function openPicker(i){slot=i;document.querySelector('dialog').showModal()}
        function pick(name){document.getElementById('s'+slot).textContent=name;document.querySelector('dialog').close()}</script></main>`);
      await prepareSwap(page, 'USDT', 'ETH', '1000');
      assert.equal(await page.locator('input').inputValue(), '1000');
      if (layout === 'select') assert.deepEqual(await page.locator('select').evaluateAll(nodes => nodes.map(node => node.value)), ['2', '0']);
      else assert.deepEqual(await page.locator('#s0,#s1').allTextContents(), [tether, 'Ether']);
    } finally { await browser.close(); }
  });
}

test('chooses the EIP-6963 Test Wallet instead of an existing dev account or legacy connector', async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage();
    const address = '0x123456789012345678901234567890123456789abc';
    await page.setContent(`<main><span id="account">status: connected 0xdead…beef</span><button id="disconnect" onclick="document.getElementById('account').textContent='disconnected';this.remove();document.querySelector('section').hidden=false">Disconnect</button>
      <section hidden><button onclick="throw Error('Dev wallet selected')">Connect Dev wallet (anvil #0)</button>
      <button onclick="throw Error('Legacy connector selected')">Injected</button></section></main>
      <script>window.addEventListener('eip6963:requestProvider',()=>{const button=document.createElement('button');button.textContent='Connect Test Wallet';
      button.onclick=()=>{document.getElementById('account').textContent='0x123456…789abc';document.querySelector('section').hidden=true};document.querySelector('section').append(button)})</script>`);
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await connect(page, address);
    assert.equal(await page.locator('#account').innerText(), '0x123456…789abc');
    assert.deepEqual(errors, []);
  } finally { await browser.close(); }
});

test('refuses an arbitrary connected status and Disconnect button', async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage();
    await page.setContent('<p>status: connected 0xdead…beef</p><button>Disconnect</button>');
    await assert.rejects(connect(page, '0x123456789012345678901234567890123456789abc'), /Test Wallet account was not connected/);
  } finally { await browser.close(); }
});

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
