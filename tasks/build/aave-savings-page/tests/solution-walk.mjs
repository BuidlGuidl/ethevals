import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import { chromium } from './deps.mjs';
import initPage from './mcp-page.mjs';

// The free check has no judge. This walk-through knows our solution's controls and runs on that exact source only.
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
for (const file of (await sourceFiles('/workspace/src').catch(() => [])).sort()) {
  digest.update(path.relative('/workspace', file) + '\0');
  digest.update(await fs.readFile(file));
  digest.update('\0');
}
if (digest.digest('hex') !== 'de66292c054e382961d0e422308d9037d6bdd8c3e6f1e023eeb0b029574929ff') process.exit(0);

const session = JSON.parse(await fs.readFile('/logs/verifier/session.json', 'utf8'));
async function command(name, args = []) {
  const response = await fetch(session.control + '/' + name, { method: 'POST', body: JSON.stringify(args) });
  if (!response.ok) throw new Error(`${name}: ${await response.text()}`);
}
const libraries = ['/root/savings-libs/usr/lib/x86_64-linux-gnu', '/root/savings-libs/usr/lib/aarch64-linux-gnu',
  '/root/savings-libs/lib/x86_64-linux-gnu', '/root/savings-libs/lib/aarch64-linux-gnu'];
process.env.PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS = '1';
const browser = await chromium.launch({ headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage'],
  env: { ...process.env, LD_LIBRARY_PATH: libraries.join(':'), FONTCONFIG_FILE: '/root/savings-fonts.conf' } });
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1100 }, serviceWorkers: 'block' });
  page.setDefaultTimeout(120_000);
  await initPage({ page });
  const card = symbol => page.locator('section.savings-card').filter({ has: page.getByRole('heading', { name: symbol, exact: true }) });
  const open = async () => {
    await page.goto(session.origin + '/#savings');
    await page.reload();
    const connect = page.getByRole('button', { name: 'Test Wallet', exact: true });
    await connect.or(card('USDC').locator('form')).first().waitFor();
    if (await connect.isVisible()) await connect.click({ timeout: 2000 }).catch(() => {});
    await card('USDC').locator('form').waitFor();
  };
  async function act(symbol, mode, amount, done) {
    const form = card(symbol).locator('form');
    await form.getByRole('tab', { name: mode === 'deposit' ? 'Deposit' : 'Withdraw', exact: true }).click();
    if (amount === 'max') await form.getByRole('button', { name: 'Max', exact: true }).click();
    else await form.getByLabel(`${mode === 'deposit' ? 'Deposit' : 'Withdraw'} amount in ${symbol}`).fill(amount);
    await form.getByRole('button', { name: `${mode === 'deposit' ? 'Deposit' : 'Withdraw'} ${symbol}`, exact: true }).click();
    await form.getByText(done, { exact: true }).waitFor();
  }
  await open();
  await act('USDC', 'deposit', '100', 'Deposited 100 USDC.');
  await command('move-time', ['30']);
  await open();
  await act('USDC', 'withdraw', '40', 'Withdrew 40 USDC.');
  await act('USDC', 'withdraw', 'max', 'Withdrew all USDC.');
  await command('old-usdt-approval');
  await act('USDT', 'deposit', '100', 'Deposited 100 USDT.');
  await command('full-cap');
  await open();
  const form = card('USDC').locator('form');
  await form.getByRole('tab', { name: 'Deposit', exact: true }).click();
  await form.getByLabel('Deposit amount in USDC').fill('6000.10');
  await form.getByText(/^Exceeds Aave's supply cap/).waitFor();
  // Our page disables Deposit here. Leave time for any wallet request the page might still send.
  await page.waitForTimeout(4000);
} catch (error) {
  const page = browser.contexts()[0]?.pages()[0];
  if (page) {
    await page.screenshot({ path: '/logs/verifier/walk-failure.png', fullPage: true }).catch(() => {});
    await fs.writeFile('/logs/verifier/walk-failure.txt', await page.locator('body').innerText().catch(() => '')).catch(() => {});
  }
  throw error;
} finally {
  await browser.close();
}
