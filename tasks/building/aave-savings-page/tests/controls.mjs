import { CouldNotDrive, firstVisible, amountInputs as inputs, createVocabulary } from './control-vocabulary.mjs';

const words = { deposit: '(?:deposit|supply)', withdraw: 'withdraw(?:al)?' };
const vocabulary = createVocabulary(words, { prerequisites: { deposit: /^(?:approve)(?: USDC| USDT)?(?: to continue)?$/i } });
const actionName = vocabulary.name;
const findSubmit = vocabulary.findSubmit;
export const submitAction = vocabulary.submit;

export async function connect(page, address) {
  await page.waitForFunction(() => document.body.innerText.trim().length > 0);
  let connected = false;
  for (let i = 0; i < 20; i++) {
    const text = await page.locator('body').innerText();
    if (/status:\s*connected/i.test(text) || text.toLowerCase().includes(address.slice(0, 6).toLowerCase())
      || await firstVisible(page.getByRole('button', { name: /^disconnect(?: wallet)?$/i }))) { connected = true; break; }
    const wallet = await firstVisible(page.getByRole('button', { name: /test wallet|metamask, rabby|^injected$|^metamask$/i }));
    if (wallet) { await wallet.click(); connected = true; break; }
    const button = await firstVisible(page.getByRole('button', { name: /^connect(?: (?:a |your )?wallet)?$/i }));
    if (button) await button.click();
    else if (await firstVisible(inputs(page))) { connected = true; break; }
    await page.waitForTimeout(250);
  }
  if (!connected) throw new CouldNotDrive('connect wallet control was not found');
  const savings = await firstVisible(page.getByRole('link', { name: /^savings$/i }));
  if (savings) await savings.click();
}

export async function tokenBlock(page, token, { controls = false } = {}) {
  const found = await page.waitForFunction(({ token, controls }) => {
    for (const el of document.querySelectorAll('[data-savings-token]')) el.removeAttribute('data-savings-token');
    const visible = el => el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden';
    const other = token === 'USDC' ? 'USDT' : 'USDC';
    const candidates = [...document.querySelectorAll('section,article,tr,div,button')].filter(el => {
      if (!visible(el) || el.closest('[role="dialog"],dialog')) return false;
      const text = el.innerText || '';
      const names = [...el.querySelectorAll('h1,h2,h3,h4,strong,span,td,p')].filter(visible).map(child => child.textContent.trim());
      if (names.includes(other)) return false;
      const namedToken = names.includes(token);
      const hasControls = el.tagName === 'BUTTON' || el.querySelector('button,input,[role="tab"]');
      return namedToken && (!controls || hasControls) && (/%|APY|deposited|your savings/i.test(text) || el.querySelector('input'));
    });
    const positionLabel = /^(?:your savings|your deposit|deposited|supplied|balance.*interest)$/i;
    const rank = el => {
      const controlRank = el.tagName === 'BUTTON' || el.querySelector('button,input,[role="tab"]') ? 10 : 0;
      if (el.tagName === 'TR' && [...el.closest('table').querySelectorAll('thead th')].some(header => /savings|deposit|supplied|balance/i.test(header.innerText) && !/wallet/i.test(header.innerText))) return controlRank + 3;
      if ([...el.querySelectorAll('dt')].some(label => /deposited|supplied/i.test(label.innerText))) return controlRank + 3;
      for (const sibling of [...el.parentElement.children].slice(0, [...el.parentElement.children].indexOf(el))) {
        if (sibling.children.length === el.children.length && [...sibling.children].some(column => positionLabel.test(column.textContent.trim()))) return controlRank + 3;
      }
      return controlRank + (/\d\s*%/.test(el.innerText) ? 1 : 0);
    };
    candidates.sort((a, b) => rank(b) - rank(a) || a.innerText.length - b.innerText.length);
    if (!candidates.length) return false;
    candidates[0].setAttribute('data-savings-token', token);
    return true;
  }, { token, controls }, { timeout: 5000 }).then(handle => handle.jsonValue()).catch(error => {
    if (error.name === 'TimeoutError') return false;
    throw error;
  });
  if (!found) throw new CouldNotDrive(`${token} block was not found`);
  return page.locator(`[data-savings-token="${token}"]`);
}

async function formScope(page, block, mode, token) {
  await page.locator('[data-savings-form]').evaluateAll(nodes => nodes.forEach(node => node.removeAttribute('data-savings-form')));
  if (await block.evaluate(el => el.tagName === 'BUTTON')) await block.click();
  if (!await firstVisible(inputs(block))) {
    const trigger = await firstVisible(block.getByRole('button', { name: actionName(mode, token, '') }));
    if (trigger) await trigger.click();
  }
  const dialog = await firstVisible(page.getByRole('dialog'));
  const base = dialog || (await firstVisible(inputs(block)) ? block : page);
  const tab = await firstVisible(base.getByRole('tab', { name: actionName(mode, token, '') }));
  if (tab) await tab.click();
  else if ((await inputs(base).all()).length <= 1) {
    const modeButton = await firstVisible(base.getByRole('button', { name: new RegExp(`^${words[mode]}$`, 'i') }));
    const other = await firstVisible(base.getByRole('button', { name: actionName(mode === 'deposit' ? 'withdraw' : 'deposit', token, '') }));
    const separateSubmit = await firstVisible(base.getByRole('button', { name: /^(?:confirm|review|approve)\b/i }))
      || await firstVisible(base.locator('form button[type="submit"]'));
    if (modeButton && other && separateSubmit && !await modeButton.evaluate(el => el.type === 'submit' && Boolean(el.closest('form')))) await modeButton.click();
  }
  const submit = await findSubmit(base, mode, token);
  if (submit) {
    for (const ancestor of (await submit.locator('xpath=ancestor::*').all()).reverse()) {
      if (await firstVisible(inputs(ancestor))) {
        await ancestor.evaluate(el => el.setAttribute('data-savings-form', 'active'));
        return page.locator('[data-savings-form="active"]');
      }
    }
  }
  // A disabled submit can initially say "Enter an amount".
  for (const form of await base.locator('form').all()) if (await form.isVisible() && await firstVisible(inputs(form))) return form;
  if (await firstVisible(inputs(base))) return base;
  throw new CouldNotDrive(`${mode} ${token} amount form was not found`);
}

export async function prepareAction(page, token, mode, amount, max = false, { allowRefusal = false } = {}) {
  const block = await tokenBlock(page, token, { controls: true });
  const scope = await formScope(page, block, mode, token);
  for (const select of await scope.getByRole('combobox').all()) {
    const value = await select.evaluate((el, token) => [...el.options].find(option => option.textContent.trim() === token)?.value, token);
    if (value !== undefined) await select.selectOption(value);
  }
  const tokenChoice = await firstVisible(scope.getByRole('button', { name: new RegExp(`^${token}$`, 'i') }));
  if (tokenChoice) await tokenChoice.click();
  const input = await firstVisible(inputs(scope));
  if (!input) throw new CouldNotDrive(`${mode} ${token} amount input was not found`);
  if (max) {
    const button = await firstVisible(scope.getByRole('button', { name: /^(?:max|all|withdraw all)(?:\b.*)?$/i }));
    if (!button) throw new CouldNotDrive(`${token} withdraw-all control was not found`);
    await button.click();
  } else {
    await input.fill(amount);
  }
  const submit = await findSubmit(scope, mode, token);
  if (!submit && !allowRefusal) throw new CouldNotDrive(`${mode} ${token} submit control was not found`);
  console.log(JSON.stringify({ event: 'prepared_action', token, mode, amount, max,
    input: await input.evaluate(el => el.outerHTML), submit: submit && await submit.evaluate(el => el.outerHTML) }));
  return { scope, input, submit, page, mode, token, allowRefusal };
}

export async function dismiss(page) {
  for (let i = 0; i < 30; i++) {
    const dialog = await firstVisible(page.getByRole('dialog'));
    if (!dialog) return;
    const close = await firstVisible(dialog.getByRole('button', { name: /^close|^done$|^cancel$/i }));
    if (close && !await close.isEnabled()) { await page.waitForTimeout(200); continue; }
    if (close) {
      try { await close.click({ timeout: 500 }); } catch { /* The dialog can close itself after confirmation. */ }
    } else await page.keyboard.press('Escape');
    await page.waitForTimeout(100);
  }
  throw new CouldNotDrive('transaction dialog could not be dismissed');
}

export async function visibleValues(page, token) {
  const block = await tokenBlock(page, token);
  return block.evaluate(el => {
    const text = el.innerText;
    const visible = node => node && node.getClientRects().length && getComputedStyle(node).visibility !== 'hidden';
    const percentages = [];
    const add = value => { for (const match of value.matchAll(/(\d+(?:\.\d+)?)\s*%/g)) percentages.push(Number(match[1])); };
    for (const node of el.querySelectorAll('*')) {
      if (!visible(node) || !/\bAPY\b/i.test(node.innerText || '')) continue;
      if ([...node.children].some(child => /\bAPY\b/i.test(child.innerText || ''))) continue;
      const own = node.innerText.trim();
      if (/%/.test(own)) add(own);
      else if (node.parentElement && /%/.test([...node.parentElement.childNodes].filter(child => child.nodeType === Node.TEXT_NODE).map(child => child.textContent).join(' '))) {
        add([...node.parentElement.childNodes].filter(child => child.nodeType === Node.TEXT_NODE).map(child => child.textContent).join(' '));
      }
      else if (visible(node.nextElementSibling) && /^\s*\d+(?:\.\d+)?\s*%\s*$/.test(node.nextElementSibling.innerText)) add(node.nextElementSibling.innerText);
      else if (visible(node.previousElementSibling) && /^\s*\d+(?:\.\d+)?\s*%\s*$/.test(node.previousElementSibling.innerText)) add(node.previousElementSibling.innerText);
    }
    const headers = el.tagName === 'TR' ? [...el.closest('table').querySelectorAll('thead tr')] : [...el.parentElement.children].slice(0, [...el.parentElement.children].indexOf(el));
    for (const header of headers) {
      const columns = [...header.children];
      const index = columns.findIndex(column => visible(column) && /\bAPY\b/i.test(column.innerText));
      if (index >= 0 && columns.length === el.children.length && visible(el.children[index])) add(el.children[index].innerText);
    }
    const numbers = [...text.replace(/\d+(?:\.\d+)?\s*%/g, '').matchAll(/[\d,]+(?:\.\d+)?/g)].map(match => Number(match[0].replaceAll(',', '')));
    return { text, percentages, numbers };
  });
}
