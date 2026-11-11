import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import { chromium } from './deps.mjs';
import initPage from './mcp-page.mjs';

// The free check can use these controls only on the exact solution source.
async function sourceFiles(directory) {
  const result = [];
  for (const entry of await fs.readdir(directory, { withFileTypes: true })) {
    const file = path.join(directory, entry.name);
    if (entry.isDirectory()) result.push(...await sourceFiles(file));
    else if (entry.isFile()) result.push(file);
  }
  return result;
}
const digest = crypto.createHash('sha256');
for (const file of (await sourceFiles('/workspace/src')).sort()) {
  digest.update(path.relative('/workspace', file) + '\0');
  digest.update(await fs.readFile(file));
  digest.update('\0');
}
if (digest.digest('hex') !== 'b9f647d28573f71f602c4a9f77deea55907fcb26842aa205a7d31d888ce708f2') process.exit(0);
const session = JSON.parse(await fs.readFile('/logs/verifier/session.json', 'utf8'));
const browser = await chromium.launch({ headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage'] });
try {
  const page = await browser.newPage();
  page.setDefaultTimeout(120_000);
  await initPage({ page });
  await page.goto(session.origin + '/#/swap');
  const connect = page.getByRole('button', { name: 'Test Wallet', exact: true });
  const amountInput = page.locator('input[inputmode="decimal"]');
  await connect.or(amountInput).first().waitFor();
  if (!await amountInput.isVisible()) await connect.click({ timeout: 1000 }).catch(() => {});
  await amountInput.waitFor();
  let input = 'ETH';
  let output = 'USDC';
  for (const [nextInput, nextOutput, amount, mode] of [
    ['ETH', 'USDC', '1', 'normal'], ['USDC', 'ETH', '500', 'normal'],
    ['USDT', 'USDC', '1000', 'normal'], ['USDT', 'USDC', '1000', 'seed'],
    ['USDC', 'ETH', '500', 'reject'], ['USDC', 'ETH', '500', 'race'],
  ]) {
    if (await page.getByRole('button', { name: 'New swap', exact: true }).count()) {
      await page.getByRole('button', { name: 'New swap', exact: true }).click();
    }
    if (await page.getByRole('button', { name: 'Back', exact: true }).count()) {
      await page.getByRole('button', { name: 'Back', exact: true }).click();
    }
    if (input !== nextInput) {
      await page.locator('.field').nth(0).getByRole('button', { name: input, exact: true }).click();
      await page.getByRole('dialog', { name: 'Choose token' }).getByRole('button', { name: nextInput, exact: true }).click();
      // Selecting the current output swaps the pair in this solution.
      if (nextInput === output) output = input;
      input = nextInput;
    }
    if (output !== nextOutput) {
      await page.locator('.field').nth(1).getByRole('button', { name: output, exact: true }).click();
      await page.getByRole('dialog', { name: 'Choose token' }).getByRole('button', { name: nextOutput, exact: true }).click();
      output = nextOutput;
    }
    const response = await fetch(session.control + '/wallet-test', { method: 'POST', body: JSON.stringify([input, output, amount, mode]) });
    if (!response.ok) throw new Error(await response.text());
    await page.locator('input[inputmode="decimal"]').fill(amount);
    await page.getByRole('button', { name: 'Review swap', exact: true }).click();
    await page.getByRole('button', { name: 'Confirm swap', exact: true }).click();
    if (mode === 'reject') await page.locator('.error').waitFor();
    else if (mode === 'race') await page.locator('.error').or(page.getByRole('heading', { name: 'Swap complete', exact: true })).first().waitFor();
    else await page.getByRole('button', { name: 'New swap', exact: true }).waitFor();
  }
} finally {
  await browser.close();
}
