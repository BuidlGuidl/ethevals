import { CouldNotDrive, firstVisible, amountInputs } from './control-vocabulary.mjs';
import { belief } from './checks.mjs';
import { until } from './harness.mjs';
import { walletIdle } from './rpc-policy.mjs';

const tokenName = /^(?:ETH|USDC|USDT)$/i;
const actionName = /^(?:(?:swap|review|confirm|approve|accept|continue|refresh|switch)\b)/i;

export async function connect(page, address) {
  await page.waitForFunction(() => document.body.innerText.trim().length > 0);
  for (let i = 0; i < 25; i++) {
    const text = await page.locator('body').innerText();
    if (/status:\s*connected/i.test(text) || text.toLowerCase().includes(address.slice(0, 6).toLowerCase())
      || await firstVisible(page.getByRole('button', { name: /^disconnect(?: wallet)?$/i }))) break;
    const wallet = await firstVisible(page.getByRole('button', { name: /test wallet|metamask, rabby|^injected$|^metamask$/i }));
    const button = wallet || await firstVisible(page.getByRole('button', { name: /^connect(?: (?:a |your )?wallet)?$/i }));
    if (button && await button.isEnabled()) await button.click();
    else {
      const connection = await firstVisible(page.getByRole('button', { name: /^(?:connection|wallet)$/i }).or(page.getByRole('link', { name: /^(?:connection|wallet)$/i })));
      if (connection && await connection.isEnabled()) await connection.click();
    }
    await page.waitForTimeout(250);
  }
  const swapLink = await firstVisible(page.getByRole('link', { name: /^swap$/i }));
  const swapButton = await firstVisible(page.getByRole('button', { name: /^swap$/i }));
  if (swapLink) await swapLink.click();
  else if (!await firstVisible(amountInputs(page)) && swapButton && await swapButton.isEnabled()) await swapButton.click();
}

async function slots(page) {
  const candidates = page.locator('select,[role="combobox"]').or(page.getByRole('button', { name: /^(?:(?:select|choose|from|to|sell|buy)\s+)?(?:ETH|USDC|USDT)(?:\s*[⌄▾▼])?$/i }));
  const result = [];
  for (const item of await candidates.all()) {
    if (!await item.isVisible()) continue;
    const valid = await item.evaluate(el => el.tagName === 'SELECT'
      ? [...el.options].some(option => /^(ETH|USDC|USDT)$/.test(option.textContent.trim()))
      : /\b(ETH|USDC|USDT)\b/.test(el.innerText || el.getAttribute('aria-label') || ''));
    if (valid) result.push(item);
  }
  return result;
}
async function slotSymbol(slot) {
  return slot.evaluate(el => (el.tagName === 'SELECT' ? el.selectedOptions[0]?.textContent : el.innerText || el.getAttribute('aria-label') || '').match(/\b(ETH|USDC|USDT)\b/)?.[1]);
}
async function choose(page, index, symbol) {
  const controls = await slots(page);
  const slot = controls[index];
  if (slot) {
    if (await slotSymbol(slot) === symbol) return;
    if (await slot.evaluate(el => el.tagName === 'SELECT')) {
      const value = await slot.evaluate((el, symbol) => [...el.options].find(option => option.textContent.trim() === symbol)?.value, symbol);
      if (value !== undefined) { await slot.selectOption(value); return; }
    }
    await slot.click();
    const popup = await firstVisible(page.getByRole('listbox').or(page.getByRole('dialog')));
    const scope = popup || page;
    const option = await firstVisible(scope.getByRole('option', { name: new RegExp(`^${symbol}(?:\\b.*)?$`, 'i') }).or(scope.getByRole('button', { name: new RegExp(`^${symbol}$`, 'i') })));
    if (option) { await option.click(); return; }
  }
  for (const role of ['tab', 'radio']) {
    const options = page.getByRole(role, { name: new RegExp(`^${symbol}$`, 'i') });
    const option = await firstVisible(options.nth(Math.min(index, await options.count() - 1)));
    if (option) { await option.click(); return; }
  }
  throw new CouldNotDrive(`pair: ${symbol} choice was not found`);
}
export async function prepareSwap(page, input, output, amount) {
  await until(async () => (await slots(page)).length >= 2, 8000);
  await choose(page, 0, input);
  await choose(page, 1, output);
  async function correctPair() {
    const controls = await slots(page);
    if (controls.length >= 2) return await slotSymbol(controls[0]) === input && await slotSymbol(controls[1]) === output;
    const selected = await page.locator('[role="tab"][aria-selected="true"],[role="radio"][aria-checked="true"],input[type="radio"]:checked').evaluateAll(nodes => nodes.map(el =>
      el.getAttribute('aria-label') || (el.labels ? [...el.labels].map(label => label.innerText).join(' ') : el.innerText)));
    return selected.map(text => text.trim()).filter(text => tokenName.test(text)).join(',') === `${input},${output}`;
  }
  if (!await correctPair()) {
    const flip = await firstVisible(page.getByRole('button', { name: /flip|swap direction|switch tokens|↓↑|⇅|↕/i }));
    if (flip && await flip.isEnabled()) await flip.click();
  }
  if (!await correctPair()) throw new CouldNotDrive(`pair: expected ${input} then ${output}`);
  const inputs = [];
  for (const item of await amountInputs(page).all()) {
    if (await item.isVisible() && await item.isEnabled() && await item.isEditable()) inputs.push(item);
  }
  let amountInput;
  for (const item of inputs) {
    if (await item.evaluate((el, token) => {
      for (let parent = el.parentElement; parent && parent.tagName !== 'BODY'; parent = parent.parentElement) {
        const controls = parent.querySelectorAll('select,[role="combobox"],button');
        if ([...controls].some(control => new RegExp(`\\b${token}\\b`).test(control.innerText || ''))) return true;
        if (parent.querySelectorAll('input').length > 1) return false;
      }
      return false;
    }, input)) { amountInput = item; break; }
  }
  amountInput ||= inputs.length === 1 ? inputs[0] : null;
  if (!amountInput) throw new CouldNotDrive('input amount');
  await amountInput.fill(amount);
  if (!await until(async () => Boolean(await nextAction(page)), 20_000)) throw new CouldNotDrive('swap quote or action');
  return { page, input, output, amount, amountInput };
}

export async function nextAction(page) {
  const dialog = await firstVisible(page.getByRole('dialog'));
  const candidates = [];
  for (const button of await (dialog || page).getByRole('button', { name: actionName }).all()) {
    if (!await button.isVisible() || !await button.isEnabled()) continue;
    const label = await button.innerText();
    const accessible = await button.getAttribute('aria-label') || label;
    if (/direction|new swap|another swap|tokens|[↓↑⇅↕]/i.test(`${label} ${accessible}`)) continue;
    const depth = await button.evaluate(el => {
      let depth = 0;
      for (let parent = el.parentElement; parent && parent.tagName !== 'BODY'; parent = parent.parentElement) {
        depth++;
        if ([...parent.querySelectorAll('input,output,dl')].some(input => input.getClientRects().length)) return depth;
      }
      return 1000;
    });
    candidates.push({ button, depth, review: /^(?:confirm|refresh|accept|continue|approve|review)\b/i.test(label) });
  }
  candidates.sort((a, b) => Number(b.review) - Number(a.review) || a.depth - b.depth);
  return candidates[0]?.button || null;
}

export async function pressThrough(action, { wallet, isSwapRequest, snapshot, beforePress = async () => {}, maxPresses = 6 }) {
  const presses = [];
  let lastBelief;
  for (let index = 0; index < maxPresses; index++) {
    const button = await nextAction(action.page);
    if (!button) break;
    const text = await action.page.locator('body').innerText();
    const label = await button.innerText();
    lastBelief = belief(text, action.output);
    const press = { index, time: Date.now(), label, text, belief: lastBelief };
    presses.push(press);
    await snapshot(press);
    await beforePress(press);
    await button.click();
    const idle = await walletIdle(wallet, { timeoutMs: 240_000 });
    if (!idle) throw new CouldNotDrive('wallet request did not settle');
    if (wallet.requests.some(isSwapRequest)) break;
    await action.page.waitForTimeout(400);
  }
  return { presses, belief: lastBelief };
}
