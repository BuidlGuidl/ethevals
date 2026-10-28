import { CouldNotDrive, firstVisible } from './control-vocabulary.mjs';
import { until } from './harness.mjs';
import { walletIdle } from './rpc-policy.mjs';
import { requestedCalls, governorAbi, votesAbi } from './chain.mjs';

export async function connect(page, address) {
  await page.waitForFunction(() => document.body.innerText.trim().length > 0, undefined, { timeout: 20000 });
  for (let step = 0; step < 30; step++) {
    const text = await page.locator('body').innerText();
    if (text.toLowerCase().includes(address.slice(0, 6).toLowerCase())) break;
    const wallet = await firstVisible(page.getByRole('button', { name: /test wallet|metamask, rabby|^injected$|^metamask$/i }));
    const connect = await firstVisible(page.getByRole('button', { name: /^connect(?: (?:a |your )?wallet)?$/i }));
    if (wallet || connect) await (wallet || connect).click();
    await page.waitForTimeout(200);
  }
  const governance = await firstVisible(governanceControls(page));
  if (governance) await governance.click();
  if (!await until(async () => (await page.locator('body').innerText()).toLowerCase().includes(address.slice(0, 6).toLowerCase()), 20000)) {
    throw new CouldNotDrive('the page did not show the funded wallet address');
  }
  return Boolean(governance);
}
export const governanceControls = page => page.getByRole('link', { name: /governance/i })
  .or(page.getByRole('button', { name: /governance/i })).or(page.getByRole('tab', { name: /governance/i }));

export async function settled(scope, { timeout = 8000, quiet = 800 } = {}) {
  let previous, since = Date.now(), text = '';
  const stable = await until(async () => {
    text = await scope.innerText();
    const controls = await scope.locator('button,input,[role="radio"]').evaluateAll(elements =>
      elements.map(el => [el.textContent, el.disabled, el.getAttribute('aria-checked')]));
    const fingerprint = JSON.stringify([text, controls]);
    if (fingerprint !== previous || /\bloading\b/i.test(text)) { previous = fingerprint; since = Date.now(); }
    return Date.now() - since >= quiet;
  }, timeout);
  if (!stable) throw new CouldNotDrive('page values or controls did not settle');
  return text;
}

export async function openProposal(page, description) {
  await dismiss(page);
  if (!await until(() => findDescription(page, description), 15000)) throw new CouldNotDrive(`proposal title ${description} was not found`);
  const title = await firstVisible(page.getByText(description, { exact: false }));
  // Locate a control container only for driving. Evidence always captures the whole visible page.
  const container = title.locator('xpath=ancestor-or-self::*[self::article or self::section or self::li or self::tr or self::button or self::a or @role="button"][1]');
  const card = await container.count() ? container : title.locator('..');
  const link = await firstVisible(card.getByRole('link').filter({ hasText: description }))
    || (await title.evaluate(el => el.matches('a[href]')) ? title : null);
  if (link) {
    const href = await link.getAttribute('href');
    if (href && new URL(href, page.url()).origin === new URL(page.url()).origin) await link.click();
  } else {
    const open = await firstVisible(card.getByRole('button', { name: /^(?:view|details|vote on)\b/i }));
    if (open) await open.click();
    else if (await card.evaluate(el => el.matches('button,[role="button"]'))) await card.click();
  }
  return await firstVisible(page.getByRole('dialog')) || card;
}

export async function findDescription(page, description, capture = async () => {}) {
  const root = new URL(page.url());
  const visible = () => firstVisible(page.getByText(description, { exact: false }));
  if (await visible()) return true;
  if (/^https?:/.test(root.protocol) && (root.pathname !== '/' || (root.hash && !/governance/i.test(root.hash)))) {
    await page.goto(root.origin, { waitUntil: 'domcontentloaded' });
    const governance = await firstVisible(governanceControls(page));
    if (governance) await governance.click();
    await until(visible, 1000);
    await capture();
    if (await visible()) return true;
  }
  const visited = new Set();
  for (let step = 0; step < 12; step++) {
    const navigation = page.getByRole('button').or(page.getByRole('tab')).or(page.getByRole('link'))
      .filter({ hasText: /^(?:all(?: proposals)?|active|open|closed|past|history|pending|next(?: page)?|[1-9]\d*)$/i });
    let next;
    for (const control of await navigation.all()) {
      const key = (await control.innerText()).trim() + ':' + (await page.locator('body').innerText());
      if (!visited.has(key) && await control.isVisible() && await control.isEnabled()) { visited.add(key); next = control; break; }
    }
    if (!next) break;
    await next.click();
    await until(visible, 1000);
    await capture();
    if (await visible()) return true;
  }
  return false;
}
export async function listedDescriptions(page, descriptions, capture = async () => {}) {
  await until(() => page.evaluate(descriptions => descriptions.some(description => document.body.innerText.includes(description)), descriptions), 15000);
  await capture();
  const listed = [];
  for (const description of descriptions) if (await findDescription(page, description, capture)) { listed.push(description); await capture(); }
  return listed;
}

export async function captureProposalList(session, descriptions, capture) {
  const listViews = [];
  const titlesFound = await listedDescriptions(session.page, descriptions, async () => {
    const text = await capture();
    if (!listViews.includes(text)) listViews.push(text);
  });
  return { titlesFound, governanceFound: session.governanceFound || await governanceControls(session.page).count() > 0,
    governor: { count: descriptions.length, titles: descriptions }, listViews };
}

export async function dismiss(page) {
  const dialog = await firstVisible(page.getByRole('dialog'));
  if (!dialog) return;
  const close = await firstVisible(dialog.getByRole('button', { name: /^(?:close|done)(?: .*)?$/i }));
  if (close) await close.click();
  else await page.keyboard.press('Escape');
}

export async function voteControl(scope, choice = 'For') {
  return await firstVisible(scope.getByRole('button', { name: new RegExp(`^(?:vote )?${choice}(?:\\s+.*)?$`, 'i') }))
    || firstVisible(scope.getByRole('radio', { name: new RegExp(`^${choice}\\b`, 'i') }));
}
export async function usableChoices(scope) {
  const page = scope.page?.() || scope;
  scope = await firstVisible(page.getByRole('dialog')) || scope;
  const choices = [];
  for (const name of ['For', 'Against', 'Abstain']) {
    const control = await voteControl(scope, name);
    if (control && await control.isEnabled()) choices.push(name);
  }
  return choices;
}
export async function castVote(session, scope, name = 'For') {
  const choice = await until(async () => voteControl(await firstVisible(session.page.getByRole('dialog')) || scope, name), 8000);
  if (!choice) throw new CouldNotDrive('Vote For control was not found');
  if (!await until(() => choice.isEnabled(), 20000)) return false;
  const count = () => requestedCalls(session.wallet, session.governor, governorAbi).filter(call => /^castVote/.test(call.functionName)).length;
  const before = count();
  await choice.click();
  const clicked = new Set();
  const done = await until(async () => {
    if (count() > before) return true;
    const dialog = await firstVisible(session.page.getByRole('dialog'));
    const submit = await firstVisible((dialog || scope).getByRole('button', { name: /^(?:(?:cast|submit|confirm)(?: (?:your )?vote(?: for)?| for(?: vote)?)?|vote(?: for)?)$/i }));
    if (submit && await submit.isEnabled()) {
      const label = await submit.innerText();
      if (!clicked.has(label)) { clicked.add(label); await submit.click(); }
    }
    return count() > before;
  }, 8000);
  if (!done) throw new CouldNotDrive('vote flow did not ask the wallet for castVote');
  await walletIdle(session.wallet);
  return true;
}

export async function wrap(session) {
  const page = session.page;
  const wrapNames = /^(?:(?:approve\s*(?:&|and)\s*)?wrap(?:\s.*)?|deposit(?: TOKEN)?|confirm(?: wrap| deposit)?)$/i;
  const trigger = await firstVisible(page.getByRole('button', { name: wrapNames }));
  if (trigger && await until(() => trigger.isEnabled(), 8000)) await trigger.click();
  const base = await firstVisible(page.getByRole('dialog')) || page;
  await until(() => base.locator('input').evaluateAll(inputs => {
    document.querySelectorAll('[data-wrap-input]').forEach(el => el.removeAttribute('data-wrap-input'));
    const candidates = inputs.filter(input => input.getClientRects().length && input.type !== 'hidden'
      && !/address|delegate|search/i.test([input.placeholder, input.getAttribute('aria-label')].join(' ')));
    if (candidates[0]) candidates[0].setAttribute('data-wrap-input', '');
    return candidates.length > 0;
  }), 8000);
  const input = page.locator('[data-wrap-input]');
  if (!await input.count()) throw new CouldNotDrive('wrap amount input was not found');
  await input.fill('1000');
  const approval = /^approve(?: TOKEN)?(?: to continue)?$/i;
  const deposits = () => requestedCalls(session.wallet, session.voteToken, votesAbi).filter(call => call.functionName === 'depositFor').length;
  const beforeDeposit = deposits();
  const scope = await firstVisible(page.getByRole('dialog')) || page;
  for (let step = 0; step < 4; step++) {
    const names = new RegExp(wrapNames.source + '|' + approval.source, 'i');
    let submit;
    for (const button of await scope.getByRole('button', { name: names }).all()) {
      if (!await button.isVisible()) continue;
      const followsInput = await button.evaluate(button => {
        const input = document.querySelector('[data-wrap-input]');
        return Boolean(input && input.compareDocumentPosition(button) & Node.DOCUMENT_POSITION_FOLLOWING);
      });
      if (followsInput) { submit = button; break; }
    }
    if (!submit) throw new CouldNotDrive('wrap or approval control was not found');
    if (!await until(() => submit.isEnabled(), 8000)) throw new CouldNotDrive('wrap control stayed disabled');
    await submit.click();
    await walletIdle(session.wallet);
    if (deposits() > beforeDeposit) return;
  }
  throw new CouldNotDrive('wrap steps did not finish');
}

export async function delegate(session, address) {
  const page = session.page;
  await dismiss(page);
  const count = () => requestedCalls(session.wallet, session.voteToken, votesAbi).filter(call => call.functionName === 'delegate').length;
  const before = count();
  const self = /^(?:delegate(?: votes)? to (?:yourself|myself|me|self)|self[ -]delegate|activate (?:my |your )?(?:votes|voting power))(?:\s.*)?$/i;
  let direct = await firstVisible(page.getByRole('button', { name: self }));
  if (!direct) {
    const open = await firstVisible(page.getByRole('button', { name: /^delegate(?: votes| voting power)?$/i }));
    if (open) {
      if (!await until(() => open.isEnabled(), 8000)) throw new CouldNotDrive('delegate control stayed disabled');
      await open.click();
    }
    if (count() === before) direct = await firstVisible(page.getByRole('button', { name: self }));
  }
  if (direct) {
    if (!await until(() => direct.isEnabled(), 8000)) throw new CouldNotDrive('self-delegate control stayed disabled');
    await direct.click();
  }
  else if (count() === before) {
    const input = await firstVisible(page.getByRole('textbox', { name: /delegate|address/i }))
      || await firstVisible(page.locator('input[placeholder*="address" i]'));
    if (input) await input.fill(address);
  }
  if (count() === before) {
    const dialog = await firstVisible(page.getByRole('dialog'));
    const submit = await firstVisible((dialog || page).getByRole('button', { name: /^(?:(?:confirm|update) delegation|delegate)$/i }));
    if (submit) {
      if (!await until(() => count() > before || submit.isEnabled(), 8000)) throw new CouldNotDrive('delegate control stayed disabled');
      if (count() === before) await submit.click();
    }
  }
  await walletIdle(session.wallet);
  if (count() === before) throw new CouldNotDrive('delegation flow did not ask the wallet to delegate');
}
