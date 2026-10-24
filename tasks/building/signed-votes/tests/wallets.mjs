import assert from 'node:assert/strict';
import {
  concatHex, createPublicClient, createTestClient, createWalletClient, encodeFunctionData,
  getAddress, hashTypedData, http, parseAbi, parseEther,
} from 'viem';
import { generatePrivateKey, privateKeyToAccount } from 'viem/accounts';
import { toCoinbaseSmartAccount } from 'viem/account-abstraction';
import { mainnet } from 'viem/chains';

export const addresses = {
  safe: '0x41675C099F32341bf84BFc5382aF534df5C7461a',
  factory: '0x4e1DCf7AD4e460CfD30791CCC4F9c8a4f820ec67',
  handler: '0xfd0732Dc9E303f09fCEf3a7388Ad10A83459Ec99',
  signMessageLib: '0xd53cd0aB83D845Ac265BE939c57F53AD838012c9',
  coinbaseFactory: '0x0BA5ED0c6AA8c49038F819E587E2633c4A9F428a',
};
const safeAbi = parseAbi([
  'function setup(address[] owners,uint256 threshold,address to,bytes data,address fallbackHandler,address paymentToken,uint256 payment,address paymentReceiver)',
  'function getThreshold() view returns (uint256)',
  'function getOwners() view returns (address[])',
]);
const factoryAbi = parseAbi([
  'function createProxyWithNonce(address singleton,bytes initializer,uint256 saltNonce) returns (address proxy)',
]);
const zero = '0x0000000000000000000000000000000000000000';
const safeMessageTypes = { SafeMessage: [{ name: 'message', type: 'bytes' }] };

export async function wallets(rpcUrl) {
  const transport = http(rpcUrl);
  const client = createPublicClient({ chain: mainnet, transport, pollingInterval: 25 });
  const control = createTestClient({ chain: mainnet, transport, mode: 'anvil' });
  const sponsor = privateKeyToAccount(generatePrivateKey());
  await control.setBalance({ address: sponsor.address, value: parseEther('100') });
  const sender = createWalletClient({ chain: mainnet, transport, account: sponsor });
  async function send(parameters) {
    const hash = await sender.sendTransaction(parameters);
    const receipt = await client.waitForTransactionReceipt({ hash });
    assert.equal(receipt.status, 'success', 'Fixture transaction succeeds');
    return receipt;
  }
  for (const [name, address] of Object.entries(addresses)) {
    assert.ok((await client.getCode({ address }))?.length > 2, `${name} has code at the pinned block`);
  }

  const owners = Array.from({ length: 3 }, () => privateKeyToAccount(generatePrivateKey()))
    .sort((a, b) => a.address.toLowerCase().localeCompare(b.address.toLowerCase()));
  const initializer = encodeFunctionData({
    abi: safeAbi, functionName: 'setup',
    args: [owners.map(owner => owner.address), 2n, zero, '0x', addresses.handler, zero, 0n, zero],
  });
  const proxyArgs = [addresses.safe, initializer, BigInt(Date.now())];
  const simulation = await client.simulateContract({
    account: sponsor, address: addresses.factory, abi: factoryAbi,
    functionName: 'createProxyWithNonce', args: proxyArgs,
  });
  const safe = simulation.result;
  await send({
    to: addresses.factory,
    data: encodeFunctionData({ abi: factoryAbi, functionName: 'createProxyWithNonce', args: proxyArgs }),
  });
  assert.equal(await client.readContract({ address: safe, abi: safeAbi, functionName: 'getThreshold' }), 2n);
  assert.deepEqual(
    (await client.readContract({ address: safe, abi: safeAbi, functionName: 'getOwners' })).map(address => address.toLowerCase()).sort(),
    owners.map(owner => owner.address.toLowerCase()).sort(),
  );

  async function safeSign(typedData, count = 2) {
    const hash = hashTypedData({
      domain: { chainId: 1, verifyingContract: safe }, types: safeMessageTypes,
      primaryType: 'SafeMessage', message: { message: hashTypedData(typedData) },
    });
    return concatHex(await Promise.all(owners.slice(0, count).map(owner => owner.sign({ hash }))));
  }

  async function smartWallet(deploy) {
    const owner = privateKeyToAccount(generatePrivateKey());
    let account = await toCoinbaseSmartAccount({ client, owners: [owner], version: '1' });
    assert.equal(await client.getCode({ address: account.address }), undefined);
    if (deploy) {
      const { factory, factoryData } = await account.getFactoryArgs();
      assert.equal(getAddress(factory), getAddress(addresses.coinbaseFactory));
      await send({ to: factory, data: factoryData });
      assert.ok((await client.getCode({ address: account.address }))?.length > 2);
      // A fresh account instance observes deployment before signing.
      account = await toCoinbaseSmartAccount({ client, owners: [owner], version: '1' });
    }
    return account;
  }

  return { client, control, safe, safeSign, smartWallet };
}
