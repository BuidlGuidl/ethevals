import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';

async function sourceFiles(directory) {
  const result = [];
  for (const entry of await fs.readdir(directory, { withFileTypes: true }).catch(error => {
    if (error.code === 'ENOENT') return [];
    throw error;
  })) {
    const file = path.join(directory, entry.name);
    if (entry.isDirectory()) result.push(...await sourceFiles(file));
    else if (entry.isFile()) result.push(file);
  }
  return result;
}

export async function requireSolutionSource(workspace, expected) {
  const digest = crypto.createHash('sha256');
  for (const file of (await sourceFiles(path.join(workspace, 'src'))).sort()) {
    digest.update(path.relative(workspace, file) + '\0');
    digest.update(await fs.readFile(file));
    digest.update('\0');
  }
  if (digest.digest('hex') !== expected) {
    throw Object.assign(new Error("The solution walk-through's source hash is out of date."), { code: 'SOLUTION_HASH' });
  }
}
