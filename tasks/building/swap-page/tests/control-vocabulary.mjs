export class CouldNotDrive extends Error {
  constructor(message) { super(`could not drive: ${message}`); }
}

export async function firstVisible(locator) {
  for (const item of await locator.all()) if (await item.isVisible()) return item;
  return null;
}

export const amountInputs = scope => scope.getByRole('textbox').or(scope.locator('input[type="number"]'));

export function createVocabulary(words, { prerequisites = {} } = {}) {
  const actionName = (mode, token, prefix = '(?:(?:review|confirm) )?') =>
    new RegExp(`^${prefix}${words[mode]}(?: all)?(?: ${token})?$`, 'i');
  async function findSubmit(scope, mode, token) {
    const local = async locator => {
      const matches = [];
      for (const button of await locator.all()) {
        if (!await button.isVisible()) continue;
        const depth = await button.evaluate(el => {
          let depth = 0;
          for (let parent = el.parentElement; parent && parent.tagName !== 'BODY'; parent = parent.parentElement) {
            depth++;
            if ([...parent.querySelectorAll('input:not([type="hidden"])')].some(input => input.getClientRects().length)) return depth;
          }
          return Infinity;
        });
        if (Number.isFinite(depth)) matches.push({ button, depth });
      }
      matches.sort((a, b) => a.depth - b.depth);
      return matches[0]?.button || null;
    };
    const candidates = scope.getByRole('button', { name: actionName(mode, token) });
    const prerequisite = prerequisites[mode] ? await local(scope.getByRole('button', { name: prerequisites[mode] })) : null;
    return await local(scope.getByRole('button', { name: actionName(mode, token, '(?:review|confirm) ') }))
      || prerequisite
      || await local(scope.locator('button[type="submit"]').filter({ hasText: actionName(mode, token) }))
      || await local(scope.getByRole('button', { name: new RegExp(`^${words[mode]}(?: all)? ${token}$`, 'i') }))
      || await local(scope.getByRole('button', { name: /^confirm$/i }))
      || await local(candidates);
  }


  async function submitAction(action, { settle = async () => {}, complete = async () => true } = {}) {
    if (!action.submit || !await action.submit.isEnabled()) return false;
    const label = await action.submit.innerText();
    try { await action.submit.click({ timeout: 10_000 }); }
    catch (error) {
      if (!await action.submit.isEnabled()) return false;
      throw error;
    }
    if (/^review\b/i.test(label)) {
      const confirm = action.page.getByRole('button', { name: new RegExp(`^confirm(?: ${words[action.mode]})?(?: ${action.token})?$`, 'i') });
      try { await confirm.first().waitFor({ state: 'visible', timeout: 5000 }); }
      catch { if (action.allowRefusal) return false; throw new CouldNotDrive('review confirmation control was not found'); }
      if (!await confirm.first().isEnabled()) return false;
      await confirm.first().click();
    }
    // Approval can be a separate user step. Do not click the same submit again.
    if (prerequisites[action.mode]?.test(label)) {
      await settle();
      for (let step = 0; step < 2 && !await complete(); step++) {
        const next = await findSubmit(action.scope, action.mode, action.token);
        if (!next || !await next.isEnabled() || prerequisites[action.mode]?.test(await next.innerText())) break;
        await next.click();
        await settle();
      }
    }
    return true;
  }


  return { name: actionName, findSubmit, submit: submitAction };
}
