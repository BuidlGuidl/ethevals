import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { requireSolutionSource } from './solution-source.mjs';

test('the walk-through accepts its source and names an outdated hash after an edit', async () => {
  const workspace = await fs.mkdtemp(path.join(os.tmpdir(), 'solution-source-'));
  try {
    await fs.mkdir(path.join(workspace, 'src'));
    const file = path.join(workspace, 'src/App.tsx');
    await fs.writeFile(file, 'export const value = 1;\n');
    const expected = '3a421e87ccf98846785483f8f38a1fa54527c72f96124b45bf3a3dcde0209a59';
    await requireSolutionSource(workspace, expected);
    await fs.writeFile(file, 'export const value = 2;\n');
    await assert.rejects(requireSolutionSource(workspace, expected), {
      code: 'SOLUTION_HASH', message: "The solution walk-through's source hash is out of date.",
    });
  } finally { await fs.rm(workspace, { recursive: true, force: true }); }
});
