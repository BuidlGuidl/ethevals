import test from 'node:test';
import assert from 'node:assert/strict';
import { chromium } from './deps.mjs';
import { createVocabulary } from './control-vocabulary.mjs';

test('copied vocabulary drives another page task without savings names', async () => {
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
  try {
    const page = await browser.newPage();
    await page.setContent(`<section><input value="2"><button onclick="document.querySelector('output').innerText='exchanged '+document.querySelector('input').value">Exchange ETH</button><output></output></section>`);
    const vocabulary = createVocabulary({ swap: '(?:swap|exchange)' });
    const submit = await vocabulary.findSubmit(page, 'swap', 'ETH');
    await vocabulary.submit({ page, scope: page, mode: 'swap', token: 'ETH', submit });
    assert.equal(await page.locator('output').innerText(), 'exchanged 2');
    assert.equal(await page.getByRole('button', { name: vocabulary.name('swap', 'ETH') }).innerText(), 'Exchange ETH');
  } finally { await browser.close(); }
});
