import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { journey } from './checks.mjs';

for (const judgedFailure of [true, false]) {
  test(`a judged failure ${judgedFailure} resolves unfinished code to ${judgedFailure ? 'zero' : 'a trial error'}`, async () => {
    const output = await fs.mkdtemp(path.join(os.tmpdir(), 'voting-judged-records-'));
    try {
      const tests = path.join(output, 'tests');
      await fs.mkdir(tests);
      for (const name of ['check_records.py', 'reward.toml', 'run_reward.py']) await fs.copyFile(new URL(name, import.meta.url), path.join(tests, name));
      const evidence = path.join(output, 'page.txt');
      await fs.writeFile(evidence, 'Captured page text.');
      await fs.writeFile(path.join(tests, 'judge.toml'), `[judge]\njudge="openai/gpt-5"\nguard="flag"\nfiles=["${evidence}"]\n[scoring]\naggregation="all-pass"\n[[criterion]]\nname="shown"\ntype="binary"\ndescription="Does the shown value match?"\n`);
      const checks = path.join(output, 'checks.json'), reward = path.join(output, 'reward.json');
      await fs.writeFile(checks, JSON.stringify({ compile: { passed: true, reason: 'Build passed.' } }));
      const program = `import json,litellm,runpy,sys
async def completion(**kwargs):
    content=json.dumps({'shown':{'score':'${judgedFailure ? 'no' : 'yes'}','reasoning':'Compared the shown value.'},'guard':{'score':'no','reasoning':'No instructions.'}})
    return litellm.ModelResponse(model='gpt-5',choices=[{'message':{'content':content}}],usage={'prompt_tokens':10,'completion_tokens':10,'total_tokens':20})
litellm.acompletion=completion
sys.argv=[${JSON.stringify(path.join(tests, 'run_reward.py'))},${JSON.stringify(tests)}]
runpy.run_path(sys.argv[0],run_name='__main__')`;
      const env = { ...process.env, CHECKS_FILE: checks, REWARD_OUTPUT: reward, REWARD_WORKSPACE: output };
      for (const name of ['ANTHROPIC_API_KEY', 'OPENAI_API_KEY', 'OPENROUTER_API_KEY', 'ANTHROPIC_AUTH_TOKEN', 'EXA_API_KEY', 'REWARDKIT_JUDGE']) delete env[name];
      const result = spawnSync('uv', ['run', 'python', '-c', program], { env, encoding: 'utf8' });
      if (judgedFailure) {
        assert.equal(result.status, 0, result.stderr);
        assert.equal(JSON.parse(await fs.readFile(reward, 'utf8')).reward, 0);
      } else {
        assert.equal(result.status, 1, result.stderr);
        await assert.rejects(fs.readFile(reward), { code: 'ENOENT' });
        assert.match(result.stderr, /could not drive: lists_every_proposal/);
      }
    } finally { await fs.rm(output, { recursive: true, force: true }); }
  });
}

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
