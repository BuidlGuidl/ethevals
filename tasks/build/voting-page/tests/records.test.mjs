import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { journey } from './checks.mjs';

test('RewardKit keeps zero after an unexpected error and missing records', async () => {
  const output = await fs.mkdtemp(path.join(os.tmpdir(), 'voting-records-'));
  try {
    const tests = path.join(output, 'tests');
    await fs.mkdir(tests);
    for (const name of ['check_records.py', 'reward.toml']) await fs.copyFile(new URL(name, import.meta.url), path.join(tests, name));
    const records = { compile: { passed: false, reason: 'The build failed.' } };
    await journey(records, 'wrap_then_delegate', async () => { throw new Error('Execution context was destroyed'); }, async () => {});
    const checks = path.join(output, 'checks.json');
    await fs.writeFile(checks, JSON.stringify(records));
    const env = { ...process.env, CHECKS_FILE: checks };
    for (const name of ['ANTHROPIC_API_KEY', 'OPENAI_API_KEY', 'OPENROUTER_API_KEY', 'ANTHROPIC_AUTH_TOKEN', 'EXA_API_KEY']) delete env[name];
    const result = spawnSync('uv', ['run', 'rewardkit', tests, '--workspace', process.cwd(), '--output', path.join(output, 'reward.json')], { env, encoding: 'utf8' });
    assert.equal(result.status, 0, result.stderr);
    assert.equal(JSON.parse(await fs.readFile(path.join(output, 'reward.json'), 'utf8')).reward, 0);
  } finally { await fs.rm(output, { recursive: true, force: true }); }
});
for (const knownFailure of [true, false]) {
  test(`missing records with known failure ${knownFailure} give ${knownFailure ? 'zero' : 'a trial error'}`, async () => {
    const output = await fs.mkdtemp(path.join(os.tmpdir(), 'voting-missing-records-'));
    try {
      const tests = path.join(output, 'tests');
      await fs.mkdir(tests);
      for (const name of ['check_records.py', 'reward.toml']) await fs.copyFile(new URL(name, import.meta.url), path.join(tests, name));
      const checks = path.join(output, 'checks.json');
      await fs.writeFile(checks, JSON.stringify({ compile: { passed: !knownFailure, reason: 'Build result.' } }));
      const env = { ...process.env, CHECKS_FILE: checks };
      for (const name of ['ANTHROPIC_API_KEY', 'OPENAI_API_KEY', 'OPENROUTER_API_KEY', 'ANTHROPIC_AUTH_TOKEN', 'EXA_API_KEY']) delete env[name];
      const reward = path.join(output, 'reward.json');
      const result = spawnSync('uv', ['run', 'rewardkit', tests, '--workspace', process.cwd(), '--output', reward], { env, encoding: 'utf8' });
      if (knownFailure) {
        assert.equal(result.status, 0, result.stderr);
        assert.equal(JSON.parse(await fs.readFile(reward, 'utf8')).reward, 0);
      } else {
        assert.equal(result.status, 1, result.stderr);
        await assert.rejects(fs.readFile(reward), { code: 'ENOENT' });
        assert.match(result.stderr, /could not drive: no record/);
      }
    } finally { await fs.rm(output, { recursive: true, force: true }); }
  });
}
