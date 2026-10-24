// Use visible text and accessible control names. Never inspect app source or React state.
export class CouldNotDrive extends Error {
  constructor(message) { super(`could not drive: ${message}`); }
}

export async function firstVisible(locator) {
  for (const item of await locator.all()) if (await item.isVisible()) return item;
  return null;
}

export async function connect(page, address) {
  await page.waitForFunction(() => document.body.innerText.trim().length > 0);
  let connected = false;
  for (let i = 0; i < 20; i++) {
    const text = await page.locator('body').innerText();
    if (/status:\s*connected/i.test(text) || text.toLowerCase().includes(address.slice(0, 6).toLowerCase())) { connected = true; break; }
    const wallet = await firstVisible(page.getByRole('button', { name: /test wallet|metamask, rabby|^injected$|^metamask$/i }));
    if (wallet) { await wallet.click(); connected = true; break; }
    const button = await firstVisible(page.getByRole('button', { name: /^connect(?: (?:a |your )?wallet)?$/i }));
    if (button) await button.click();
    await page.waitForTimeout(250);
  }
  if (!connected) throw new CouldNotDrive('connect wallet control was not found');
  const savings = await firstVisible(page.getByRole('link', { name: /^savings$/i }));
  if (savings) await savings.click();
}

export async function tokenBlock(page, token) {
  const found = await page.evaluate(token => {
    for (const el of document.querySelectorAll('[data-savings-token]')) el.removeAttribute('data-savings-token');
    const visible = el => el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden';
    const other = token === 'USDC' ? 'USDT' : 'USDC';
    const candidates = [...document.querySelectorAll('section,article,tr,div,button')].filter(el => {
      if (!visible(el) || el.closest('[role="dialog"],dialog')) return false;
      const text = el.innerText || '';
      const names = [...el.querySelectorAll('h1,h2,h3,h4,strong,span,td')].map(child => child.textContent.trim());
      if (names.includes(other)) return false;
      const namedToken = names.includes(token);
      const action = el.tagName === 'BUTTON' || [...el.querySelectorAll('button,[role="tab"]')].some(button => /deposit|supply|withdraw|select/i.test(button.getAttribute('aria-label') || button.innerText));
      return namedToken && action && /%|APY|deposited|your savings/i.test(text);
    });
    const positionLabel = /^(?:your savings|your deposit|deposited|supplied|balance.*interest)$/i;
    const rank = el => {
      if (el.tagName === 'TR' && [...el.closest('table').querySelectorAll('thead th')].some(header => /savings|deposit|supplied|balance/i.test(header.innerText) && !/wallet/i.test(header.innerText))) return 3;
      if ([...el.querySelectorAll('dt')].some(label => /deposited|supplied/i.test(label.innerText))) return 3;
      for (const sibling of [...el.parentElement.children].slice(0, [...el.parentElement.children].indexOf(el))) {
        if (sibling.children.length === el.children.length && [...sibling.children].some(column => positionLabel.test(column.textContent.trim()))) return 3;
      }
      return /\d\s*%/.test(el.innerText) ? 1 : 0;
    };
    candidates.sort((a, b) => rank(b) - rank(a) || a.innerText.length - b.innerText.length);
    if (!candidates.length) return false;
    candidates[0].setAttribute('data-savings-token', token);
    return true;
  }, token);
  if (!found) throw new CouldNotDrive(`${token} block was not found`);
  return page.locator(`[data-savings-token="${token}"]`);
}

async function formScope(page, block, mode, token) {
  if (await block.evaluate(el => el.tagName === 'BUTTON')) await block.click();
  const input = await firstVisible(block.getByRole('textbox').or(block.locator('input[type="number"]')));
  // Card forms either have one form with tabs, or one form per action.
  if (input) {
    const tab = await firstVisible(block.getByRole('tab', { name: new RegExp(`^${mode}$`, 'i') }));
    if (tab) await tab.click();
    const forms = block.locator('form').filter({ has: page.getByRole('button', { name: new RegExp(`^${mode}(?: ${token})?$`, 'i') }) });
    const form = await firstVisible(forms);
    return form || block;
  }
  const trigger = await firstVisible(block.getByRole('button', { name: new RegExp(`^${mode}(?: ${token})?$`, 'i') }));
  if (trigger) await trigger.click();
  // Some pages open a dialog, others select a persistent transaction form.
  const dialog = await firstVisible(page.getByRole('dialog'));
  if (dialog) {
    const tab = await firstVisible(dialog.getByRole('button', { name: new RegExp(`^${mode}$`, 'i') }).or(dialog.getByRole('tab', { name: new RegExp(`^${mode}$`, 'i') })));
    if (tab) await tab.click();
    return dialog;
  }
  const tab = await firstVisible(page.getByRole('button', { name: new RegExp(`^${mode}$`, 'i') }).or(page.getByRole('tab', { name: new RegExp(`^${mode}$`, 'i') })));
  if (tab) await tab.click();
  const forms = page.locator('form').filter({ has: page.locator('input:not([type="hidden"])') });
  for (const form of await forms.all()) {
    if (!await form.isVisible()) continue;
    if (await form.getByRole('button', { name: new RegExp(`^${mode}(?: ${token})?$|^switch to ethereum$`, 'i') }).count()) return form;
    if (await form.locator('input[inputmode="decimal"]').count() && await form.locator('button[type="submit"]').count()) return form;
  }
  // An action panel can use click handlers without an HTML form element.
  for (const input of await page.getByRole('textbox').or(page.locator('input[type="number"]')).all()) {
    if (!await input.isVisible()) continue;
    const ancestors = await input.locator('xpath=ancestor::*[self::section or self::div]').all();
    for (const ancestor of ancestors.reverse()) {
      const submit = await firstVisible(ancestor.getByRole('button', { name: new RegExp(`^(?:review )?${mode === 'withdraw' ? 'withdraw(?:al)?' : mode}(?: USDC| USDT)?$`, 'i') }));
      if (submit) return ancestor;
    }
  }
  throw new CouldNotDrive(`${mode} ${token} amount form was not found`);
}

export async function prepareAction(page, token, mode, amount, max = false) {
  const block = await tokenBlock(page, token);
  const scope = await formScope(page, block, mode, token);
  for (const select of await scope.getByRole('combobox').all()) {
    const value = await select.evaluate((el, token) => [...el.options].find(option => option.textContent.trim() === token)?.value, token);
    if (value !== undefined) await select.selectOption(value);
  }
  const tokenChoice = await firstVisible(scope.getByRole('button', { name: new RegExp(`^${token}$`, 'i') }));
  if (tokenChoice) await tokenChoice.click();
  const input = await firstVisible(scope.getByRole('textbox').or(scope.locator('input[type="number"]')));
  if (!input) throw new CouldNotDrive(`${mode} ${token} amount input was not found`);
  if (max) {
    const button = await firstVisible(scope.getByRole('button', { name: /^(?:max|all|withdraw all)(?:\b.*)?$/i }));
    if (!button) throw new CouldNotDrive(`${token} withdraw-all control was not found`);
    await button.click();
  } else {
    await input.fill(amount);
  }
  const noun = mode === 'withdraw' ? 'withdraw(?:al)?' : 'deposit';
  const submit = await firstVisible(scope.getByRole('button', { name: new RegExp(`^(?:review|confirm) ${noun}(?: ${token})?$`, 'i') }))
    || await firstVisible(scope.getByRole('button', { name: new RegExp(`^${mode}(?: all)? ${token}$`, 'i') }))
    || await firstVisible(scope.locator('button[type="submit"]').filter({ hasText: new RegExp(`^${mode}$`, 'i') }))
    || await firstVisible(scope.getByRole('button', { name: new RegExp(`^${mode}$|^confirm$`, 'i') }));
  if (!submit) throw new CouldNotDrive(`${mode} ${token} submit control was not found`);
  console.log(JSON.stringify({ event: 'prepared_action', token, mode, amount, max,
    input: await input.evaluate(el => el.outerHTML), submit: await submit.evaluate(el => el.outerHTML) }));
  return { scope, input, submit, page };
}

export async function submitAction(action) {
  const label = await action.submit.innerText();
  try { await action.submit.click({ timeout: 10_000 }); }
  catch (error) {
    if (!await action.submit.isEnabled()) return false;
    throw error;
  }
  if (/^review\b/i.test(label)) {
    const confirm = action.page.getByRole('button', { name: /^confirm(?: (?:deposit|withdrawal|withdraw))?(?: USDC| USDT)?$/i });
    try { await confirm.first().waitFor({ state: 'visible', timeout: 5000 }); }
    catch { throw new CouldNotDrive('review confirmation control was not found'); }
    await confirm.first().click();
  }
  return true;
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
    const percentages = [...text.matchAll(/(\d+(?:\.\d+)?)\s*%/g)].map(match => Number(match[1]));
    const balances = [];
    const label = /^(?:deposited(?:\s*\(.*\))?|your savings|your deposit|supplied|saved|deposited balance)$/i;
    for (const child of el.querySelectorAll('dt,label,span,small,div,p')) {
      if (label.test(child.textContent.trim()) && child.nextElementSibling) balances.push(child.nextElementSibling.innerText);
    }
    if (el.tagName === 'TR') {
      const headers = [...el.closest('table').querySelectorAll('thead th')];
      const index = headers.findIndex(header => /savings|deposit|supplied|saved|balance/i.test(header.innerText) && !/wallet/i.test(header.innerText));
      if (index >= 0) balances.push(el.children[index]?.innerText || '');
    }
    // A div-based table uses the same column order as its visible header row.
    const siblings = [...el.parentElement.children];
    for (const sibling of siblings.slice(0, siblings.indexOf(el))) {
      const columns = [...sibling.children];
      const index = columns.findIndex(column => /^(?:your savings|your deposit|deposited|supplied|balance.*interest)$/i.test(column.textContent.trim()));
      if (index >= 0 && columns.length === el.children.length) balances.push(el.children[index].innerText);
    }
    const numbers = balances.flatMap(value => [...value.matchAll(/[\d,]+(?:\.\d+)?/g)].map(match => Number(match[0].replaceAll(',', ''))));
    return { text, percentages, balances, numbers };
  });
}
