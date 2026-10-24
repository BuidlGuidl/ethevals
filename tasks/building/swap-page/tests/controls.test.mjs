import test from 'node:test';
import assert from 'node:assert/strict';
import { chromium } from './deps.mjs';
import { prepareSwap, pressThrough } from './controls.mjs';

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
    const result = await pressThrough(action, { wallet, isSwapRequest: () => false, maxPresses: 2, snapshot: async press => saved.push(press) });
    assert.deepEqual(await page.locator('select').evaluateAll(nodes => nodes.map(node => node.value)), ['USDC', 'ETH']);
    assert.equal(await page.locator('input').inputValue(), '500');
    assert.equal(await page.locator('output').innerText(), 'sent');
    assert.equal(result.belief.minimum.value, 190000000000000000n);
    assert.deepEqual(saved.map(press => press.label), ['Review swap', 'Confirm swap']);
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
