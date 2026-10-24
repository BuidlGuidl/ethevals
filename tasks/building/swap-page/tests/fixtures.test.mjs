import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import { belief, deltas, feeCheck, finiteDeadline, allowancesEmpty, routersEmpty, minimumCheck, receivedCheck } from './checks.mjs';
import { hasSwapLog } from './chain.mjs';

const root = process.env.SWAP_FIXTURE_OUTPUT;
const parse = text => JSON.parse(text, (_key, value) => typeof value === 'string' && /^\d+$/.test(value) ? BigInt(value) : value);
for (const [page, expectedFailures] of [['opus-final', []], ['kimi-final', ['cut_only_on_swap', 'finite_deadline']], ['solution-picker', []]]) {
  test(`saved chain and browser evidence for ${page}`, { skip: !root }, async () => {
    const directory = path.join(root, page);
    const read = async name => parse(await fs.readFile(path.join(directory, name), 'utf8'));
    const baseline = await read('fixture.json');
    const results = [];
    for (const [name, input, output] of [['usdc-eth', 'USDC', 'ETH'], ['eth-usdc', 'ETH', 'USDC'], ['usdt-eth', 'USDT', 'ETH'], ['moved', 'USDC', 'ETH'], ['rejected', 'USDC', 'ETH'], ['reverted', 'USDC', 'ETH']]) {
      const before = await read(`${name}-before.json`);
      const after = await read(`${name}-after.json`);
      const txs = await read(`${name}-transactions.json`);
      const delta = deltas(before, after, txs);
      const swaps = txs.filter(tx => tx.relevant);
      const success = swaps.some(tx => tx.receipt.status === '0x1' && hasSwapLog(tx.receipt)) && delta.user[output] > 0n && delta.user[input] < 0n;
      assert.equal(success, !['rejected', 'reverted'].includes(name), `${page}/${name}: receipt and balance outcome`);
      assert.equal(feeCheck(delta, input, output, success), !(page === 'kimi-final' && !success), `${page}/${name}: fee`);
      if (swaps.length) assert.equal(swaps.every(tx => finiteDeadline(tx.decoded)), !expectedFailures.includes('finite_deadline'), `${page}/${name}: deadline`);
      if (success) {
        const presses = await read(`${name}-presses.json`);
        const last = belief(presses.at(-1).text, output);
        for (const tx of swaps) assert.equal(minimumCheck(last, tx.decoded, output, delta.user[output]).passed, true, `${page}/${name}: minimum`);
        assert.equal(allowancesEmpty(after), true, `${page}/${name}: allowances`);
        if (output === 'ETH') assert.equal(delta.user.WETH, 0n, `${page}/${name}: ETH arrives unwrapped`);
        assert.equal(routersEmpty(baseline, after), true, `${page}/${name}: routers`);
        assert.equal(receivedCheck(await fs.readFile(path.join(directory, `${name}-page.txt`), 'utf8'), output, delta.user[output]).passed, true, `${page}/${name}: received`);
      }
      results.push(name);
    }
    assert.equal(results.length, 6);
  });
}
