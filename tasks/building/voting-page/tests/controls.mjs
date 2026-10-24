import { CouldNotDrive, firstVisible } from './control-vocabulary.mjs';
import { until } from './harness.mjs';
import { walletIdle } from './rpc-policy.mjs';
import { requestedCalls, governorAbi, votesAbi } from './chain.mjs';

const quantity = '(\\d[\\d,]*(?:\\.\\d+)?\\s*[KMB]?)';
export function number(text) {
  const match = text.trim().match(/^(\d[\d,]*(?:\.\d+)?)\s*([KMB])?$/i);
  if (!match) return null;
  return Number(match[1].replaceAll(',', '')) * ({ k: 1e3, m: 1e6, b: 1e9 }[match[2]?.toLowerCase()] || 1);
}
export function labelled(text, label) {
  const match = text.match(new RegExp(`(?:^|\\n|[·|])\\s*(?:${label})\\s*[:\\t\\n]?\\s*(?:\\d[\\d,.]*\\s*%\\s*[·|:]*\\s*)?${quantity}(?![\\d.,]|\\s*%)`, 'i'));
  return match ? number(match[1]) : null;
}
const statuses = [ /^(?:pending|upcoming)$/i, /^(?:active|open|open for voting)$/i,
  /^cancel(?:l)?ed$/i, /^(?:defeated|failed|rejected)$/i, /^(?:succeeded|passed)$/i,
  /^queued(?:\s.*)?$/i, /^expired$/i, /^executed$/i ];
export function proposalValues(text) {
  const lines = text.split('\n').map(line => line.trim());
  const statusLine = lines.find(line => /^status\s*:/i.test(line));
  let status = -1;
  for (const line of statusLine ? [statusLine.replace(/^status\s*:\s*/i, '')] : lines) {
    status = statuses.findIndex(expression => expression.test(line));
    if (status >= 0) break;
  }
  const quorumLine = text.match(/quorum[^\n]*(?:\n[^\n]+){0,2}/i)?.[0] || '';
  const reached = /\bnot\s+(?:yet\s+)?(?:reached|met)\b|\bunmet\b|\bbelow\b/i.test(quorumLine) ? false
    : /(?:reached|met)\b/i.test(quorumLine) ? true
    : /quorum\s*(\d+(?:\.\d+)?)\s*%/i.test(quorumLine)
      ? Number(quorumLine.match(/quorum\s*(\d+(?:\.\d+)?)\s*%/i)[1]) >= 100 : null;
  const quorumMatch = quorumLine.match(new RegExp(`(?:of|/)\\s*${quantity}`, 'i'))
    || quorumLine.match(new RegExp(`${quantity}\\s*required`, 'i'))
    || quorumLine.match(new RegExp(`quorum\\s*:?\\s*${quantity}(?![\\d.,]|\\s*%)`, 'i'));
  const endLine = text.match(/(?:\bends?\b|\bended\b|\bdeadline\b|\bcloses\b)[^\n]*(?:\n[^\n]+){0,1}/i)?.[0]
    || text.match(/^[^\n]*\b(?:left|remaining)\b[^\n]*$/im)?.[0] || '';
  const endMatch = endLine.match(/\bblock\s*([\d,]+)/i);
  const duration = [...endLine.matchAll(/(\d+)\s*(days?|hours?|minutes?|seconds?|[dhms])\b/gi)];
  const dateText = endLine.replace(/^.*?(?:ends?|ended|deadline|closes)\s*(?:at|on|in|:)?\s*/i, '').split('\n')[0];
  const date = /[a-z]|\d{4}-\d{2}-\d{2}/i.test(dateText) ? Date.parse(dateText) : NaN;
  const end = endMatch ? Number(endMatch[1].replaceAll(',', '')) : duration.length
    ? duration.reduce((sum, match) => sum + Number(match[1]) * ({ d: 86400, h: 3600, m: 60, s: 1 }[match[2][0].toLowerCase()]), 0)
    : Number.isFinite(date) ? date : null;
  const snapshot = labelled(text, '(?:your snapshot votes|(?:your )?(?:votes|voting power|weight) (?:at|for) (?:the )?(?:snapshot|this proposal)|votes you will cast|your votes (?:on|for) this proposal|eligible votes|(?:your )?(?:vote )?weight)')
    ?? (text.match(new RegExp(`you have\\s*${quantity}\\s*votes? (?:on|for) this proposal`, 'i'))?.[1]
      ? number(text.match(new RegExp(`you have\\s*${quantity}\\s*votes? (?:on|for) this proposal`, 'i'))[1]) : null)
    ?? (text.match(new RegExp(`you had\\s*${quantity}\\s*votes?[^\\n]*snapshot`, 'i'))?.[1]
      ? number(text.match(new RegExp(`you had\\s*${quantity}\\s*votes?[^\\n]*snapshot`, 'i'))[1]) : null);
  const noVotes = /you (?:had|have) no votes[^\n]*(?:snapshot|at block)|(?:snapshot[^\n]*no votes)/i.test(text);
  return { status: status < 0 ? null : status, for: labelled(text, '(?:votes? )?for'),
    against: labelled(text, '(?:votes? )?against'), reached,
    quorum: quorumMatch ? number(quorumMatch[1]) : null,
    end, endUnit: end === null ? null : endMatch ? 'block' : duration.length ? 'seconds' : 'date',
    snapshot: snapshot ?? (noVotes ? 0 : null) };
}

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
    if (fingerprint !== previous || /\bloading\b|please wait/i.test(text)) { previous = fingerprint; since = Date.now(); }
    return Date.now() - since >= quiet;
  }, timeout);
  if (!stable) throw new CouldNotDrive('page values or controls did not settle');
  return text;
}

export async function proposal(page, description, { required = true } = {}) {
  await findDescription(page, description);
  const detail = await firstVisible(page.getByRole('link').filter({ hasText: description }));
  if (detail) await detail.click();
  else {
    const candidate = page.locator('article,section,li,tr').filter({ hasText: description }).first();
    if (await candidate.count()) {
      const open = await firstVisible(candidate.getByRole('button', { name: /^(?:view|details|vote on)\b/i }));
      const text = await candidate.innerText();
      if (open && (!/\bfor\b/i.test(text) || !/\bagainst\b/i.test(text))) await open.click();
    }
  }
  const found = await until(() => page.evaluate(description => {
    document.querySelectorAll('[data-voting-proposal]').forEach(el => el.removeAttribute('data-voting-proposal'));
    const candidates = [...document.querySelectorAll('article,section,li,tr,div,dialog,[role="dialog"]')].filter(el =>
      el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden'
      && el.innerText.includes(description)
      && /\bfor\b/i.test(el.innerText) && /\bagainst\b/i.test(el.innerText));
    candidates.sort((a, b) => a.innerText.length - b.innerText.length);
    if (!candidates.length) return false;
    candidates[0].setAttribute('data-voting-proposal', '');
    return true;
  }, description), 8000);
  if (!found) {
    if (required) throw new CouldNotDrive(`proposal card for ${description} was not found`);
    return null;
  }
  return page.locator('[data-voting-proposal]');
}

export async function findDescription(page, description) {
  const root = new URL(page.url());
  const visible = () => firstVisible(page.getByText(description, { exact: false }));
  if (await visible()) return true;
  if (/^https?:/.test(root.protocol) && (root.pathname !== '/' || (root.hash && !/governance/i.test(root.hash)))) {
    await page.goto(root.origin, { waitUntil: 'domcontentloaded' });
    const governance = await firstVisible(governanceControls(page));
    if (governance) await governance.click();
    await settled(page.locator('body'));
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
    await settled(page.locator('body'));
    if (await visible()) return true;
  }
  return false;
}
export async function listedDescriptions(page, descriptions) {
  await until(() => page.evaluate(descriptions => descriptions.some(description => document.body.innerText.includes(description)), descriptions), 15000);
  const listed = [];
  for (const description of descriptions) if (await findDescription(page, description)) listed.push(description);
  return listed;
}

export async function dismiss(page) {
  const dialog = await firstVisible(page.getByRole('dialog'));
  if (!dialog) return;
  const close = await firstVisible(dialog.getByRole('button', { name: /^(?:close|done)(?: .*)?$/i }));
  if (close) await close.click();
  else await page.keyboard.press('Escape');
}

export async function votingScope(page, description) {
  const card = await proposal(page, description);
  const open = await firstVisible(card.getByRole('button', { name: /^(?:vote on|view)\b/i }));
  if (open) await open.click();
  return await firstVisible(page.getByRole('dialog')) || card;
}

export async function voteControl(scope, choice = 'For') {
  return await firstVisible(scope.getByRole('button', { name: new RegExp(`^(?:vote )?${choice}(?:\\s+.*)?$`, 'i') }))
    || firstVisible(scope.getByRole('radio', { name: new RegExp(`^${choice}\\b`, 'i') }));
}
export async function usableChoices(scope) {
  const choices = [];
  for (const name of ['For', 'Against', 'Abstain']) {
    const control = await voteControl(scope, name);
    if (control && await control.isEnabled()) choices.push(name);
  }
  return choices;
}
export async function oldVoteView(scope) {
  let text = await settled(scope, { quiet: 1500 });
  let shown = proposalValues(text).snapshot;
  let choices = await usableChoices(scope);
  if (shown !== 0 && !choices.length) {
    await until(async () => {
      text = await scope.innerText();
      shown = proposalValues(text).snapshot;
      choices = await usableChoices(scope);
      return shown === 0 || choices.length > 0;
    }, 8000);
    text = await settled(scope);
    shown = proposalValues(text).snapshot;
    choices = await usableChoices(scope);
  }
  return { text, shown, choices };
}
export async function castVote(session, scope, name = 'For') {
  const choice = await voteControl(scope, name);
  if (!choice) throw new CouldNotDrive('Vote For control was not found');
  if (!await choice.isEnabled()) return false;
  const count = () => requestedCalls(session.wallet, session.governor, governorAbi).filter(call => /^castVote/.test(call.functionName)).length;
  const before = count();
  await choice.click();
  const clicked = new Set();
  const done = await until(async () => {
    if (count() > before) return true;
    const dialog = await firstVisible(session.page.getByRole('dialog'));
    const submit = await firstVisible((dialog || scope).getByRole('button', { name: /^(?:(?:cast|submit|confirm)(?: (?:your )?vote)?(?: for)?|vote(?: for)?)$/i }));
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

export async function currentVotes(page) {
  return page.evaluate(() => {
    const visible = el => el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden';
    const candidates = [...document.querySelectorAll('section,article,div,table')].filter(el => visible(el)
      && /voting power|voting weight|your votes/i.test(el.innerText) && /wrapped|vtoken/i.test(el.innerText));
    candidates.sort((a,b) => a.innerText.length - b.innerText.length);
    return candidates.map(el => el.innerText);
  }).then(texts => texts.map(text => {
    const direct = labelled(text, 'your votes|votes|voting weight|voting power');
    const before = text.match(new RegExp(`(?:your voting power)\\s*${quantity}\\s*votes`, 'i'));
    return direct ?? (before ? number(before[1]) : null);
  }).find(value => value !== null) ?? null);
}

export async function wrap(session) {
  const page = session.page;
  const wrapNames = /^(?:(?:approve\s*(?:&|and)\s*)?wrap(?:\s.*)?|deposit(?: TOKEN)?|confirm(?: wrap| deposit)?)$/i;
  const trigger = await firstVisible(page.getByRole('button', { name: wrapNames }));
  if (trigger && await trigger.isEnabled()) await trigger.click();
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
    const open = await firstVisible(page.getByRole('button', { name: /^delegate(?: votes)?$/i }));
    if (open) await open.click();
    direct = await firstVisible(page.getByRole('button', { name: self }));
  }
  if (direct && await direct.isEnabled()) await direct.click();
  else {
    const input = await firstVisible(page.getByRole('textbox', { name: /delegate|address/i }))
      || await firstVisible(page.locator('input[placeholder*="address" i]'));
    if (input) await input.fill(address);
  }
  const dialog = await firstVisible(page.getByRole('dialog'));
  const submit = await firstVisible((dialog || page).getByRole('button', { name: /^(?:confirm delegation|delegate)$/i }));
  if (submit && await submit.isEnabled()) await submit.click();
  await walletIdle(session.wallet);
  if (count() === before) throw new CouldNotDrive('delegation flow did not ask the wallet to delegate');
}
