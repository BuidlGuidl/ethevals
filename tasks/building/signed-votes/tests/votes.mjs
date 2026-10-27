import assert from 'node:assert/strict';
import { mkdir, writeFile } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
import { generatePrivateKey, privateKeyToAccount } from 'viem/accounts';
import { wallets } from './wallets.mjs';

const [submission, output] = process.argv.slice(2);
const names = [
  'eoa_vote', 'tampered_vote', 'wrong_signer', 'other_proposal', 'safe_vote', 'safe_one_owner',
  'safe_late_vote', 'safe_onchain_approval', 'safe_onchain_unapproved', 'smart_wallet_new', 'smart_wallet_new_reused',
  'smart_wallet_deployed',
];
const records = {};
await mkdir(output, { recursive: true });
async function save() {
  await writeFile(`${output}/checks.json`, `${JSON.stringify(records, null, 2)}\n`);
}
async function timed(operation) {
  let timer;
  try {
    return await Promise.race([
      Promise.resolve().then(operation),
      new Promise((_, reject) => { timer = setTimeout(() => reject(new Error('Module call exceeded 15 seconds')), 15_000); }),
    ]);
  } finally { clearTimeout(timer); }
}

let module;
try {
  module = await timed(() => import(pathToFileURL(submission).href));
  assert.equal(typeof module.voteToSign, 'function');
  assert.equal(typeof module.checkVote, 'function');
  records.compile = { passed: true, reason: 'The module loads and exports voteToSign and checkVote.' };
} catch {
  records.compile = { passed: false, reason: 'src/votes.ts must load and export voteToSign and checkVote.' };
  for (const name of names) records[name] = { passed: false, reason: 'The module did not load.' };
  await save();
  process.exit(0);
}
await save();

const fixture = await wallets(process.env.RPC_URL);
const eoa = privateKeyToAccount(generatePrivateKey());
const stranger = privateKeyToAccount(generatePrivateKey());
let proposalId = 1000n;
async function vote(voter, support = 1, proposal = ++proposalId) {
  const fields = { proposalId: proposal, voter, support };
  return { fields, typedData: await timed(() => module.voteToSign(fields)) };
}
async function accepts(vote, signature, expected) {
  const accepted = await timed(async () => {
    try {
      return await module.checkVote(vote.fields, signature);
    } catch {
      return false;
    }
  });
  assert.equal(accepted, expected);
}
async function check(name, run, prerequisite) {
  if (prerequisite && !records[prerequisite].passed) {
    records[name] = { passed: false, reason: `The matching positive check ${prerequisite} failed.` };
  } else {
    try {
      await run();
      records[name] = { passed: true, reason: 'The module returned the required boolean for this wallet and vote.' };
    } catch (error) {
      console.error(name, String(error?.shortMessage ?? error?.message ?? error).slice(0, 1000));
      records[name] = {
        passed: false,
        reason: error?.code === 'ERR_ASSERTION' ? 'The module returned the wrong value.' : 'The module could not handle this vote.',
      };
    }
  }
  await save();
}

await check('eoa_vote', async () => {
  for (const support of [0, 1, 2]) {
    const data = await vote(eoa.address, support);
    await accepts(data, await eoa.signTypedData(data.typedData), true);
  }
});
await check('tampered_vote', async () => {
  const proposal = ++proposalId;
  const original = await vote(eoa.address, 1, proposal);
  const changed = await vote(eoa.address, 2, proposal);
  await accepts(changed, await eoa.signTypedData(original.typedData), false);
}, 'eoa_vote');
await check('wrong_signer', async () => {
  const data = await vote(eoa.address);
  await accepts(data, await stranger.signTypedData(data.typedData), false);
}, 'eoa_vote');
await check('other_proposal', async () => {
  const original = await vote(eoa.address);
  const changed = await vote(eoa.address);
  await accepts(changed, await eoa.signTypedData(original.typedData), false);
}, 'eoa_vote');
await check('safe_vote', async () => {
  const data = await vote(fixture.safe);
  const signature = await fixture.safeSign(data.typedData);
  assert.equal(await fixture.client.verifyTypedData({ ...data.typedData, address: fixture.safe, signature }), true);
  await accepts(data, signature, true);
});
await check('safe_one_owner', async () => {
  const data = await vote(fixture.safe);
  await accepts(data, await fixture.safeSign(data.typedData, 1), false);
}, 'safe_vote');
await check('safe_late_vote', async () => {
  const data = await vote(fixture.safe);
  const before = await fixture.client.getBlock({ blockTag: 'latest' });
  await fixture.control.increaseTime({ seconds: 40 * 60 * 60 });
  await fixture.control.mine({ blocks: 1 });
  const after = await fixture.client.getBlock({ blockTag: 'latest' });
  const elapsed = after.timestamp - before.timestamp;
  assert.ok(elapsed >= 144000n, 'The verifier fork advances by at least 40 hours');
  console.log('safe_late_vote elapsed seconds:', String(elapsed));
  const signature = await fixture.safeSign(data.typedData);
  assert.equal(await fixture.client.verifyTypedData({ ...data.typedData, address: fixture.safe, signature }), true);
  await accepts(data, signature, true);
});
await check('safe_onchain_approval', async () => {
  const data = await vote(fixture.safe);
  await fixture.approveSafeMessage(data.typedData);
  await accepts(data, '0x', true);
});
await check('safe_onchain_unapproved', async () => {
  const data = await vote(fixture.safe, 0);
  await accepts(data, '0x', false);
}, 'safe_onchain_approval');
await check('smart_wallet_new', async () => {
  const account = await fixture.smartWallet(false);
  const data = await vote(account.address);
  const signature = await account.signTypedData(data.typedData);
  assert.ok(signature.endsWith('6492649264926492649264926492649264926492649264926492649264926492'));
  assert.equal(await fixture.client.verifyTypedData({ ...data.typedData, address: account.address, signature }), true);
  await accepts(data, signature, true);
  assert.equal(await fixture.client.getCode({ address: account.address }), undefined);
});
await check('smart_wallet_new_reused', async () => {
  const account = await fixture.smartWallet(false);
  const original = await vote(account.address);
  const changed = await vote(account.address);
  const signature = await account.signTypedData(original.typedData);
  assert.ok(signature.endsWith('6492649264926492649264926492649264926492649264926492649264926492'));
  await accepts(changed, signature, false);
}, 'smart_wallet_new');
await check('smart_wallet_deployed', async () => {
  const account = await fixture.smartWallet(true);
  const data = await vote(account.address);
  const signature = await account.signTypedData(data.typedData);
  assert.ok(!signature.endsWith('6492649264926492649264926492649264926492649264926492649264926492'));
  assert.equal(await fixture.client.verifyTypedData({ ...data.typedData, address: account.address, signature }), true);
  await accepts(data, signature, true);
});
