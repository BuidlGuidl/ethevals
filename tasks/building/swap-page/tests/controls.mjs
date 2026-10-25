import { belief } from './checks.mjs';
import { until } from './harness.mjs';
import { walletIdle } from './rpc-policy.mjs';

const tokenAliases = { ETH: 'ETH|Ether', USDC: 'USDC|USD Coin', USDT: 'USDT|Tether USD|Tether' };
const tokenPattern = Object.values(tokenAliases).join('|');
const tokenSymbol = text => Object.keys(tokenAliases).find(symbol => new RegExp(`\\b(?:${tokenAliases[symbol]})\\b`, 'i').test(text || ''));
const actionName = /^(?:(?:swap|review|confirm|approve|accept|continue|refresh|switch)\b)/i;

export class CouldNotDrive extends Error {
  constructor(message) { super(`could not drive: ${message}`); }
}
export async function firstVisible(locator) {
  for (const item of await locator.all()) if (await item.isVisible()) return item;
  return null;
}
export const amountInputs = scope => scope.getByRole('textbox').or(scope.locator('input[type="number"]'));

export async function connect(page, address) {
  await page.waitForFunction(() => document.body.innerText.trim().length > 0);
  await page.evaluate(() => window.dispatchEvent(new Event('eip6963:requestProvider')));
  const accountName = new RegExp(`${address}\\b|${address.slice(0, 6)}[a-f0-9]*(?:…|\\.\\.\\.)[a-f0-9]*${address.slice(-4)}\\b`, 'i');
  let connected = false;
  for (let i = 0; i < 25; i++) {
    const text = await page.locator('body').innerText();
    if (accountName.test(text)) { connected = true; break; }
    const wallet = await firstVisible(page.getByRole('button', { name: /^(?:connect\s+)?test wallet$/i }));
    const legacy = i >= 4 ? await firstVisible(page.getByRole('button', { name: /^(?:connect\s+)?(?:injected|browser wallet|metamask)$/i })) : null;
    const disconnect = await firstVisible(page.getByRole('button', { name: /^disconnect(?: wallet)?$/i }));
    const button = disconnect || wallet || legacy || await firstVisible(page.getByRole('button', { name: /^connect(?: (?:a |your )?wallet)?$/i }));
    if (button && await button.isEnabled()) await button.click();
    else {
      const connection = await firstVisible(page.getByRole('button', { name: /^(?:connection|wallet)$/i }).or(page.getByRole('link', { name: /^(?:connection|wallet)$/i })));
      if (connection && await connection.isEnabled()) await connection.click();
    }
    await page.waitForTimeout(250);
  }
  if (!connected) throw new CouldNotDrive('injected Test Wallet account was not connected');
  const swapLink = await firstVisible(page.getByRole('link', { name: /^swap$/i }));
  const swapButton = await firstVisible(page.getByRole('button', { name: /^swap$/i }));
  if (swapLink) await swapLink.click();
  else if (!await firstVisible(amountInputs(page)) && swapButton && await swapButton.isEnabled()) await swapButton.click();
}

async function slots(page) {
  const candidates = page.locator('select,[role="combobox"]').or(page.getByRole('button'));
  const result = [];
  for (const item of await candidates.all()) {
    if (!await item.isVisible()) continue;
    const rank = await item.evaluate((el, pattern) => {
      const text = `${el.innerText || ''} ${el.getAttribute('aria-label') || ''} ${[...el.querySelectorAll('img[alt]')].map(image => image.alt).join(' ')}`;
      const names = new RegExp(`\\b(?:${pattern})\\b`, 'i');
      const token = el.tagName === 'SELECT' ? [...el.options].some(option => names.test(option.textContent))
        : names.test(text) || /(?:select|choose).*(?:token|input|output)/i.test(text);
      if (!token || /^(?:swap|approve|review|confirm|switch|refresh)\b/i.test(text.trim())) return null;
      let distance = 100;
      for (let parent = el.parentElement, depth = 0; parent && parent.tagName !== 'BODY'; parent = parent.parentElement, depth++) {
        if (parent.querySelector('input:not([type="hidden"]),output')) { distance = depth; break; }
      }
      if (distance === 100) return null;
      const label = /\b(input|from|sell)\b/i.test(text) ? 0 : /\b(output|to|buy)\b/i.test(text) ? 1 : null;
      return { label, distance };
    }, tokenPattern);
    if (rank) result.push({ item, order: result.length, ...rank });
  }
  const nearest = result.sort((a, b) => a.distance - b.distance).slice(0, 2).sort((a, b) => a.order - b.order);
  // Explicit slot labels take precedence; DOM order resolves unlabeled controls.
  if (nearest.some(slot => slot.label !== null)) nearest.sort((a, b) => (a.label ?? 0.5) - (b.label ?? 0.5));
  return nearest.map(slot => slot.item);
}
async function slotSymbol(slot) {
  return tokenSymbol(await slot.evaluate(el => el.tagName === 'SELECT' ? el.selectedOptions[0]?.textContent
    : `${el.innerText || ''} ${el.getAttribute('aria-label') || ''} ${[...el.querySelectorAll('img[alt]')].map(image => image.alt).join(' ')}`));
}
async function choose(page, index, symbol) {
  const controls = await slots(page);
  const slot = controls[index];
  if (slot) {
    if (await slotSymbol(slot) === symbol) return;
    if (await slot.evaluate(el => el.tagName === 'SELECT')) {
      const value = await slot.evaluate((el, aliases) => [...el.options].find(option => new RegExp(`\\b(?:${aliases})\\b`, 'i').test(option.textContent))?.value, tokenAliases[symbol]);
      if (value !== undefined) { await slot.selectOption(value); return; }
    }
    await slot.click();
    const popup = await firstVisible(page.getByRole('listbox').or(page.getByRole('dialog')));
    const scope = popup || page;
    const name = new RegExp(`\\b(?:${tokenAliases[symbol]})\\b`, 'i');
    const option = await firstVisible(scope.getByRole('option', { name }).or(scope.getByRole('button', { name })));
    if (option) { await option.click(); return; }
  }
  for (const role of ['tab', 'radio']) {
    const options = page.getByRole(role, { name: new RegExp(`^(?:${tokenAliases[symbol]})$`, 'i') });
    const option = await firstVisible(options.nth(Math.min(index, await options.count() - 1)));
    if (option) {
      if (!await option.isEnabled()) {
        const flip = await firstVisible(page.getByRole('button', { name: /flip|(?:swap|switch) direction|^switch$|switch tokens|↓↑|⇅|↕/i }));
        if (!flip || !await flip.isEnabled()) throw new CouldNotDrive(`pair: ${symbol} choice was disabled`);
        await flip.click();
      }
      await option.click(); return;
    }
  }
  throw new CouldNotDrive(`pair: ${symbol} choice was not found`);
}
export async function prepareSwap(page, input, output, amount) {
  await until(async () => (await slots(page)).length >= 2 || await page.getByRole('radio').count() >= 2 || await page.getByRole('tab').count() >= 2, 8000);
  await choose(page, 0, input);
  await choose(page, 1, output);
  async function correctPair() {
    const controls = await slots(page);
    if (controls.length >= 2) return await slotSymbol(controls[0]) === input && await slotSymbol(controls[1]) === output;
    const selected = await page.locator('[role="tab"][aria-selected="true"],[role="radio"][aria-checked="true"],input[type="radio"]:checked').evaluateAll(nodes => nodes.map(el =>
      el.getAttribute('aria-label') || (el.labels ? [...el.labels].map(label => label.innerText).join(' ') : el.innerText)));
    return selected.map(tokenSymbol).filter(Boolean).join(',') === `${input},${output}`;
  }
  if (!await correctPair()) {
    const flip = await firstVisible(page.getByRole('button', { name: /flip|(?:swap|switch) direction|^switch$|switch tokens|↓↑|⇅|↕/i }));
    if (flip && await flip.isEnabled()) await flip.click();
  }
  if (!await correctPair()) throw new CouldNotDrive(`pair: expected ${input} then ${output}`);
  const inputs = [];
  for (const item of await amountInputs(page).all()) {
    if (await item.isVisible() && await item.isEnabled() && await item.isEditable()) inputs.push(item);
  }
  let amountInput;
  const inputSlot = (await slots(page))[0];
  const inputControl = inputSlot ? await inputSlot.elementHandle() : null;
  for (const item of inputs) {
    if (inputControl && await item.evaluate((el, slot) => {
      for (let parent = el.parentElement; parent && parent.tagName !== 'BODY'; parent = parent.parentElement) {
        if (parent.querySelectorAll('input').length > 1) return false;
        if (parent.contains(slot)) return true;
      }
      return false;
    }, inputControl)) { amountInput = item; break; }
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
    if (/direction|new swap|another swap|tokens|[↓↑⇅↕]/i.test(`${label} ${accessible}`) || /^switch$/i.test(accessible.trim())) continue;
    const depth = await button.evaluate(el => {
      let depth = 0;
      for (let parent = el.parentElement; parent && parent.tagName !== 'BODY'; parent = parent.parentElement) {
        depth++;
        if ([...parent.querySelectorAll('input,output,dl')].some(input => input.getClientRects().length)) return depth;
      }
      return 1000;
    });
    const priority = /^refresh\b/i.test(accessible) ? 2 : /^(?:confirm|accept|continue|approve|review)\b/i.test(accessible) ? 0 : 1;
    candidates.push({ button, depth, priority });
  }
  candidates.sort((a, b) => a.priority - b.priority || a.depth - b.depth);
  return candidates[0]?.button || null;
}

export async function pressThrough(action, { wallet, isSwapRequest, snapshot, maxPresses = 6 }) {
  for (let index = 0; index < maxPresses; index++) {
    const button = await nextAction(action.page);
    if (!button) break;
    const text = await action.page.locator('body').innerText();
    const label = await button.innerText();
    const press = { index, time: Date.now(), label, text, belief: belief(text, action.output) };
    await snapshot(press);
    await button.click();
    const idle = await walletIdle(wallet, { timeoutMs: 240_000 });
    if (!idle) throw new CouldNotDrive('wallet request did not settle');
    if (wallet.requests.some(isSwapRequest)) break;
    await action.page.waitForTimeout(400);
  }
}
