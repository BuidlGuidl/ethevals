import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { encodeFunctionData, parseAbi } from './deps.mjs';
import { pool, USDC } from './chain.mjs';

const context = process.env.SAVINGS_FIXTURE_CHAIN_CONTEXT;
const here = path.dirname(fileURLToPath(import.meta.url));
const variants = {
  correct: {}, principal: { shows_deposit: false }, snapshot: { withdraw_all: false },
  'approve-only': { refuses_over_cap: false },
  'deposit-alias': { refuses_over_cap: false },
  'wrong-recipient': { withdraw_partial: false, withdraw_all: false },
  hardhat: {}, 'non-atomic': {}, 'simulate-first': {}, clamp: { refuses_over_cap: false },
};
for (const [variant, expected] of Object.entries(variants)) {
  test(`full verifier on ${variant} page`, { skip: !context, timeout: 300_000 }, async () => {
    const root = await fs.mkdtemp(path.join(process.env.SAVINGS_FIXTURE_OUTPUT || os.tmpdir(), `savings-${variant}-`));
    const workspace = path.join(root, 'app');
    const output = path.join(root, 'evidence');
    await fs.mkdir(path.join(workspace, 'dist'), { recursive: true });
    await fs.mkdir(output);
    const selectors = {
      '__RESERVE_SELECTOR__': encodeFunctionData({ abi: pool, functionName: 'getReserveData', args: [USDC] }).slice(0, 10),
      '__INCOME_SELECTOR__': encodeFunctionData({ abi: pool, functionName: 'getReserveNormalizedIncome', args: [USDC] }).slice(0, 10),
      '__EXECUTE_SELECTOR__': encodeFunctionData({ abi: parseAbi(['function execute((address to,uint256 value,bytes data)[] calls) payable']), functionName: 'execute', args: [[]] }).slice(0, 10),
      '__SIMULATION_BYTECODE__': (await fs.readFile(path.join(here, 'wallet-bytecode.txt'), 'utf8')).trim(),
    };
    let fixture = await fs.readFile(path.join(here, 'fixtures/savings.html'), 'utf8');
    for (const [name, value] of Object.entries(selectors)) fixture = fixture.replaceAll(name, value);
    await fs.writeFile(path.join(workspace, 'dist/index.html'), fixture.replace('data-fixture="correct"', `data-fixture="${variant}"`));
    await fs.writeFile(path.join(output, 'checks.json'), JSON.stringify({ compile: { passed: true, reason: 'Static fixture' } }));
    const log = await fs.open(path.join(root, 'browser.log'), 'w');
    const child = spawn(process.execPath, [path.join(here, 'browser.mjs'), workspace, output, context], { stdio: ['ignore', log.fd, log.fd] });
    const exit = await new Promise(resolve => child.once('exit', resolve));
    await log.close();
    assert.equal(exit, 0, root);
    const checks = JSON.parse(await fs.readFile(path.join(output, 'checks.json'), 'utf8'));
    assert.deepEqual(Object.keys(checks).sort(), ['compile', 'deposit_usdc', 'shows_deposit', 'shows_apy', 'withdraw_partial', 'withdraw_all', 'deposit_usdt_leftover_allowance', 'refuses_over_cap'].sort());
    for (const [name, result] of Object.entries(checks)) assert.equal(result.passed, expected[name] ?? true, `${root}: ${name}: ${result.reason}`);
    const initial = JSON.parse(await fs.readFile(path.join(output, 'fixture.json')));
    const capped = JSON.parse(await fs.readFile(path.join(output, 'cap-setup.json')));
    assert.equal(initial.cap, capped.previousCap);
    assert.ok(BigInt(initial.cap) > BigInt(capped.cap));
    if (variant === 'non-atomic') {
      const normal = JSON.parse(await fs.readFile(path.join(output, 'deposit-usdc-wallet.json')));
      assert.equal(normal.transactions.length, 2);
    }
    if (variant === 'simulate-first') {
      const normal = JSON.parse(await fs.readFile(path.join(output, 'deposit-usdc-wallet.json')));
      const cap = JSON.parse(await fs.readFile(path.join(output, 'cap-wallet.json')));
      assert.equal(normal.transactions.length, 2);
      assert.equal(cap.transactions.length, 0);
      assert.equal(cap.requests.filter(request => request.method === 'eth_call' && request.params[2]).length, 1);
      assert.equal(cap.requests.some(request => request.method === 'eth_call' && request.params[0].data.startsWith(selectors.__RESERVE_SELECTOR__)), false);
    }
    if (variant === 'clamp') {
      const cap = JSON.parse(await fs.readFile(path.join(output, 'cap-room.json')));
      assert.equal(cap.supplies[0].args[1], cap.room);
      assert.notEqual(cap.supplies[0].args[1], cap.oversized);
    }
  });
}
