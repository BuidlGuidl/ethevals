import assert from 'node:assert/strict';
import { readFile, writeFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
import path from 'node:path';

const require = createRequire(path.join(process.env.VERIFIER_DEPS, 'package.json'));
const {
  concatHex, createPublicClient, createWalletClient, createTestClient, defineChain, http,
  parseAbi, encodeFunctionData, hashTypedData,
} = require('viem');
const { privateKeyToAccount, generatePrivateKey } = require('viem/accounts');
const [workspace, artifactPath, output] = process.argv.slice(2);
const context = JSON.parse(await readFile(path.join(workspace, 'chain_context.json'), 'utf8'));
const artifact = JSON.parse(await readFile(artifactPath, 'utf8'));
const chain = defineChain({
  id: 1, name: 'Ethereum fork', nativeCurrency: { name: 'Ether', symbol: 'ETH', decimals: 18 },
  rpcUrls: { default: { http: [context.rpcUrl] } },
});
const transport = http(context.rpcUrl, { retryCount: 0 });
const client = createPublicClient({ chain, transport, cacheTime: 0 });
const control = createTestClient({ chain, transport, mode: 'anvil' });
const wallet = account => createWalletClient({ account, chain, transport });
const USDC = '0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48';
const VAULT = '0xBc65ad17c5C0a2A4D159fa5a503f4992c7B545FE';
const HOLDER = '0x55FE002aefF02F77364de339a1292923A15844B8';
const SAFE = '0x41675C099F32341bf84BFc5382aF534df5C7461a';
const FACTORY = '0x4e1DCf7AD4e460CfD30791CCC4F9c8a4f820ec67';
const HANDLER = '0xfd0732Dc9E303f09fCEf3a7388Ad10A83459Ec99';
const ZERO = '0x0000000000000000000000000000000000000000';
const token = parseAbi([
  'function balanceOf(address) view returns (uint256)',
  'function allowance(address,address) view returns (uint256)',
  'function transfer(address,uint256) returns (bool)',
  'function previewDeposit(uint256) view returns (uint256)',
  'function permit(address owner,address spender,uint256 value,uint256 deadline,bytes signature)',
  'function transferWithAuthorization(address from,address to,uint256 value,uint256 validAfter,uint256 validBefore,bytes32 nonce,bytes signature)',
  'function receiveWithAuthorization(address from,address to,uint256 value,uint256 validAfter,uint256 validBefore,bytes32 nonce,bytes signature)',
]);
const safeAbi = parseAbi([
  'function setup(address[] owners,uint256 threshold,address to,bytes data,address fallbackHandler,address paymentToken,uint256 payment,address paymentReceiver)',
  'function getThreshold() view returns (uint256)',
  'function getOwners() view returns (address[])',
  'function isValidSignature(bytes32 hash,bytes signature) view returns (bytes4)',
]);
const factoryAbi = parseAbi([
  'function createProxyWithNonce(address singleton,bytes initializer,uint256 saltNonce) returns (address proxy)',
]);
const names = ['compile', 'deposit_lands', 'signature_used_first', 'two_pending', 'safe_depositor', 'no_replay'];
const records = Object.fromEntries(names.map(name => [name, { passed: false, reason: 'The check has not completed.' }]));
async function save() {
  await writeFile(path.join(output, 'checks.json'), JSON.stringify(records, null, 2) + '\n');
}
let prepareDeposit;
try {
  ({ prepareDeposit } = await import(pathToFileURL(path.join(workspace, 'script/deposits.ts')).href));
  assert.equal(typeof prepareDeposit, 'function', 'prepareDeposit must be a function');
} catch (error) {
  for (const name of names) records[name] = { passed: false, reason: `Helper import failed: ${error.message}` };
  await save();
  process.exit(0);
}
await save();

const account = () => privateKeyToAccount(generatePrivateKey());
const balance = (address, owner) => client.readContract({
  address, abi: token, functionName: 'balanceOf', args: [owner],
});
async function receipt(hash) {
  // Snapshot rollback can repeat block numbers, so poll receipts without a block watcher.
  for (let attempt = 0; attempt < 500; attempt++) {
    try { return await client.getTransactionReceipt({ hash }); } catch (error) {
      if (error.name !== 'TransactionReceiptNotFoundError') throw error;
    }
    await new Promise(resolve => setTimeout(resolve, 20));
  }
  throw new Error(`The private fork did not mine transaction ${hash}`);
}
const fees = { maxFeePerGas: 100_000_000_000n, maxPriorityFeePerGas: 1_000_000_000n };
async function trySend(sender, tx) {
  return receipt(await wallet(sender).sendTransaction({ ...fees, ...tx, gas: 3_000_000n }));
}
async function mustSend(sender, tx) {
  const result = await trySend(sender, tx);
  if (result.status !== 'success') throw new Error(`The transaction to ${tx.to} reverted`);
  return result;
}
async function safeDepositor(keeper) {
  for (const address of [SAFE, FACTORY, HANDLER]) {
    assert.ok((await client.getCode({ address }))?.length > 2, 'The Safe fixture must use deployed mainnet contracts');
  }
  const owners = Array.from({ length: 3 }, account)
    .sort((a, b) => a.address.toLowerCase().localeCompare(b.address.toLowerCase()));
  const initializer = encodeFunctionData({
    abi: safeAbi, functionName: 'setup',
    args: [owners.map(owner => owner.address), 2n, ZERO, '0x', HANDLER, ZERO, 0n, ZERO],
  });
  const args = [SAFE, initializer, BigInt(generatePrivateKey())];
  const simulation = await client.simulateContract({
    account: keeper, address: FACTORY, abi: factoryAbi, functionName: 'createProxyWithNonce', args,
  });
  const address = simulation.result;
  await mustSend(keeper, { to: FACTORY, data: encodeFunctionData({ abi: factoryAbi, functionName: 'createProxyWithNonce', args }) });
  assert.equal(await client.readContract({ address, abi: safeAbi, functionName: 'getThreshold' }), 2n);
  assert.deepEqual(
    (await client.readContract({ address, abi: safeAbi, functionName: 'getOwners' })).map(value => value.toLowerCase()).sort(),
    owners.map(owner => owner.address.toLowerCase()).sort(),
  );
  return {
    address,
    async signTypedData(typedData) {
      const digest = hashTypedData(typedData);
      const hash = hashTypedData({
        domain: { chainId: 1, verifyingContract: address },
        types: { SafeMessage: [{ name: 'message', type: 'bytes' }] },
        primaryType: 'SafeMessage', message: { message: digest },
      });
      const signature = concatHex(await Promise.all(owners.slice(0, 2).map(owner => owner.sign({ hash }))));
      assert.equal(await client.readContract({
        address, abi: safeAbi, functionName: 'isValidSignature', args: [digest, signature],
      }), '0x1626ba7e', 'The Safe must accept the two sorted owner signatures');
      return signature;
    },
  };
}
async function fixture(useSafe = false) {
  const keeper = account();
  const attacker = account();
  for (const owner of [keeper.address, attacker.address, HOLDER]) {
    await control.setBalance({ address: owner, value: 10n ** 20n });
  }
  const depositor = useSafe ? await safeDepositor(keeper) : account();
  await control.impersonateAccount({ address: HOLDER });
  try {
    await mustSend(HOLDER, { to: USDC, data: encodeFunctionData({
      abi: token, functionName: 'transfer', args: [depositor.address, 20_000_000_000n],
    }) });
  } finally {
    await control.stopImpersonatingAccount({ address: HOLDER });
  }
  const deployment = await receipt(await wallet(keeper).deployContract({
    ...fees, abi: artifact.abi, bytecode: artifact.bytecode.object, args: [], gas: 5_000_000n,
  }));
  assert.equal(deployment.status, 'success', 'The no-argument deployment must succeed');
  assert.ok(deployment.contractAddress);
  for (const spender of [deployment.contractAddress, VAULT]) {
    assert.equal(await client.readContract({
      address: USDC, abi: token, functionName: 'allowance', args: [depositor.address, spender],
    }), 0n, 'The depositor starts without approvals');
  }
  return { depositor, keeper, attacker, contract: deployment.contractAddress };
}
async function signed(f, amount) {
  const prepared = await prepareDeposit({ contract: f.contract, depositor: f.depositor.address, amount });
  assert.equal(typeof prepared?.keeperTx, 'function', 'prepareDeposit must return keeperTx');
  const signature = await f.depositor.signTypedData(prepared.typedData);
  const tx = await prepared.keeperTx(signature);
  assert.equal(typeof tx?.to, 'string', 'keeperTx(signature) must give a to address');
  assert.match(tx?.data, /^0x[0-9a-fA-F]+$/);
  return { tx, signature, typedData: prepared.typedData };
}
async function state(f) {
  return {
    usdc: await balance(USDC, f.depositor.address),
    shares: await balance(VAULT, f.depositor.address),
    keeperUsdc: await balance(USDC, f.keeper.address),
    keeperShares: await balance(VAULT, f.keeper.address),
    contractUsdc: await balance(USDC, f.contract),
    contractShares: await balance(VAULT, f.contract),
    attackerUsdc: await balance(USDC, f.attacker.address),
    attackerShares: await balance(VAULT, f.attacker.address),
  };
}
async function lands(f, amount, tx, initialState) {
  const before = initialState ?? await state(f);
  const result = await mustSend(f.keeper, tx);
  const after = await state(f);
  const expected = await client.readContract({
    address: VAULT, abi: token, functionName: 'previewDeposit', args: [amount], blockNumber: result.blockNumber,
  });
  assert.equal(before.usdc - after.usdc, amount, 'The depositor must pay the full amount');
  assert.ok(expected > 0n, 'The live vault must quote nonzero shares');
  assert.ok(after.shares - before.shares >= expected, 'The depositor must get at least previewDeposit(amount) shares');
  assert.equal(after.keeperUsdc, before.keeperUsdc, 'The keeper must not supply USDC');
  assert.equal(after.keeperShares, before.keeperShares, 'The keeper must not get shares');
  assert.equal(after.attackerUsdc, before.attackerUsdc, 'The other account must not supply or receive USDC');
  assert.equal(after.attackerShares, before.attackerShares, 'The other account must not get shares');
  assert.equal(after.contractUsdc, 0n, 'The contract must retain no USDC');
  assert.equal(after.contractShares, 0n, 'The contract must retain no shares');
}
async function submitTokenAuthorization(f, { typedData, signature }) {
  const m = typedData.message;
  let functionName;
  let args;
  switch (typedData.primaryType) {
    case 'Permit':
      functionName = 'permit';
      args = [m.owner, m.spender, m.value, m.deadline, signature];
      break;
    case 'TransferWithAuthorization':
    case 'ReceiveWithAuthorization':
      functionName = typedData.primaryType === 'TransferWithAuthorization' ? 'transferWithAuthorization' : 'receiveWithAuthorization';
      args = [m.from, m.to, m.value, m.validAfter, m.validBefore, m.nonce, signature];
      break;
    default:
      return 'The typed data has no direct USDC authorization entry point.';
  }
  const result = await trySend(f.attacker, { to: USDC, data: encodeFunctionData({ abi: token, functionName, args }) });
  return `The prior USDC ${functionName} submission ${result.status === 'success' ? 'succeeded' : 'reverted'}.`;
}
async function isolated(body) {
  const snapshot = await control.snapshot();
  try { return await body(); } finally { await control.revert({ id: snapshot }); }
}
try {
  await isolated(async () => {
    const f = await fixture();
    await signed(f, 2_001_234_567n);
  });
  records.compile = { passed: true, reason: 'The contract built and the helper prepared a signable keeper transaction.' };
} catch (error) {
  for (const name of names) records[name] = {
    passed: false, reason: `Helper interface failed: ${(error.shortMessage ?? error.message).replace(/\s+/g, ' ').trim()}`,
  };
  await save();
  process.exit(0);
}
const cases = {
  async deposit_lands() {
    const f = await fixture();
    const amount = 2_137_123_456n;
    await lands(f, amount, (await signed(f, amount)).tx);
  },
  async signature_used_first() {
    const f = await fixture();
    const amount = 3_009_654_321n;
    const prepared = await signed(f, amount);
    const before = await state(f);
    const detail = await submitTokenAuthorization(f, prepared);
    await lands(f, amount, prepared.tx, before);
    return `${detail} The keeper completed the deposit.`;
  },
  async two_pending() {
    const f = await fixture();
    const first = 1_234_000_000n;
    const second = 2_345_000_000n;
    const tx1 = (await signed(f, first)).tx;
    const tx2 = (await signed(f, second)).tx;
    await lands(f, first, tx1);
    await lands(f, second, tx2);
  },
  async safe_depositor() {
    const f = await fixture(true);
    const amount = 4_001_234_567n;
    await lands(f, amount, (await signed(f, amount)).tx);
  },
  async no_replay() {
    assert.equal(records.deposit_lands.passed, true, 'Replay protection counts only after deposit_lands passes');
    const f = await fixture();
    const amount = 1_001_000_000n;
    const { tx } = await signed(f, amount);
    await lands(f, amount, tx);
    const before = await state(f);
    await trySend(f.keeper, tx);
    assert.deepEqual(await state(f), before, 'A replay must move no USDC or shares');
  },
};
for (const [name, body] of Object.entries(cases)) {
  try {
    const detail = await isolated(body);
    records[name] = { passed: true, reason: detail ?? 'The signed deposit produced the required onchain balances.' };
  } catch (error) {
    records[name] = { passed: false, reason: (error.shortMessage ?? error.message).replace(/\s+/g, ' ').trim() };
  }
  await save();
}
process.exit(0);
