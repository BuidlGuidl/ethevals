import { createWalletClient, defineChain, http, encodeFunctionData, parseAbi, toHex } from './deps.mjs';

export const POOL = '0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2';
export const USDC = '0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48';
export const USDT = '0xdAC17F958D2ee523a2206206994597C13D831ec7';
export const AUSDC = '0x98C23E9d8f34FEFb1B7BD6a91B7FF122F4e16F5c';
export const AUSDT = '0x23878914EFE38d27C4D67Ab83ed1b93A74D4086a';
export const erc20 = parseAbi([
  'function balanceOf(address) view returns (uint256)',
  'function totalSupply() view returns (uint256)',
  'function allowance(address,address) view returns (uint256)',
  'function approve(address,uint256)', 'function transfer(address,uint256)',
]);
export const pool = parseAbi([
  'function supply(address,uint256,address,uint16)',
  'function supplyWithPermit(address,uint256,address,uint16,uint256,uint8,bytes32,bytes32)',
  'function withdraw(address,uint256,address) returns (uint256)',
  'function getReserveData(address) view returns (uint256,uint128,uint128,uint128,uint128,uint128,uint40,uint16,address,address,address,address,uint128,uint128,uint128)',
  'function getReserveNormalizedIncome(address) view returns (uint256)',
]);
export const batch = parseAbi(['function execute((address to,uint256 value,bytes data)[] calls) payable']);

export async function rpc(url, method, params = []) {
  const response = await fetch(url, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ jsonrpc: '2.0', id: 1, method, params }),
    signal: AbortSignal.timeout(20_000),
  });
  const data = await response.json();
  if (data.error) {
    const error = new Error(data.error.message);
    Object.assign(error, { code: data.error.code, data: data.error.data });
    throw error;
  }
  return data.result;
}

export async function read(url, address, abi, functionName, args = []) {
  return rpc(url, 'eth_call', [{ to: address, data: encodeFunctionData({ abi, functionName, args }) }, 'latest']);
}
export const balance = async (url, token, owner) => BigInt(await read(url, token, erc20, 'balanceOf', [owner]));

export async function receipt(url, hash) {
  for (let i = 0; i < 100; i++) {
    const result = await rpc(url, 'eth_getTransactionReceipt', [hash]);
    if (result) return result;
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  throw new Error(`No receipt for ${hash}`);
}

export async function send(url, account, tx, chainId = 1) {
  const chain = defineChain({ id: chainId, name: 'Test chain', nativeCurrency: { name: 'Ether', symbol: 'ETH', decimals: 18 }, rpcUrls: { default: { http: [url] } } });
  const client = createWalletClient({ account, chain, transport: http(url) });
  const hash = await client.sendTransaction({
    to: tx.to, data: tx.data || tx.input || '0x', value: BigInt(tx.value || 0),
    gas: tx.gas ? BigInt(tx.gas) : 3_000_000n,
    gasPrice: 0n, type: 'legacy',
  });
  const mined = await receipt(url, hash);
  return { hash, receipt: mined };
}

export async function fund(url, account) {
  await rpc(url, 'anvil_setBalance', [account.address, toHex(10n ** 19n)]);
  for (const [token, holder] of [
    [USDC, '0x28C6c06298d514Db089934071355E5743bf21d60'],
    [USDT, '0xF977814e90dA44bFA03b6295A0616a897441aceC'],
  ]) {
    await rpc(url, 'anvil_impersonateAccount', [holder]);
    try {
      const hash = await rpc(url, 'eth_sendTransaction', [{ from: holder, to: token, gasPrice: '0x0', gas: '0x493e0', data: encodeFunctionData({ abi: erc20, functionName: 'transfer', args: [account.address, 10_000_000_000n] }) }]);
      if ((await receipt(url, hash)).status !== '0x1') throw new Error('Token funding failed');
    } finally {
      await rpc(url, 'anvil_stopImpersonatingAccount', [holder]);
    }
    if (await balance(url, token, account.address) !== 10_000_000_000n) throw new Error('Test wallet funding mismatch');
  }
}

export async function reserve(url) {
  const raw = await read(url, POOL, pool, 'getReserveData', [USDC]);
  const words = raw.slice(2).match(/.{64}/g).map(word => BigInt(`0x${word}`));
  const cap = ((words[0] >> 116n) & ((1n << 36n) - 1n)) * 1_000_000n;
  const total = BigInt(await read(url, AUSDC, erc20, 'totalSupply'));
  const income = BigInt(await read(url, POOL, pool, 'getReserveNormalizedIncome', [USDC]));
  const supplied = total + (words[12] * income + 5n * 10n ** 26n) / 10n ** 27n;
  const apr = Number(words[2]) / 1e27;
  return { cap, total, supplied, room: cap > supplied ? cap - supplied : 0n, apy: Math.expm1(31_536_000 * Math.log1p(apr / 31_536_000)) * 100 };
}
