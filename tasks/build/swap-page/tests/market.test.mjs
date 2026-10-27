import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { createMarket } from './market.mjs';

test('a market fixture failure is an infrastructure error', async () => {
  const output = await fs.mkdtemp(path.join(os.tmpdir(), 'swap-market-'));
  try {
    const market = createMarket({ url: 'http://127.0.0.1:1', output });
    await assert.rejects(market.moveMarket(2, 'eth-buyers'), error => error.infrastructure === true);
  } finally { await fs.rm(output, { recursive: true, force: true }); }
});
