import { encodeFunctionData, decodeFunctionData, parseAbi } from './deps.mjs';
import { rpc, read, balance, receipt, tokenAbi as erc20 } from './rpc.mjs';
export { tokenAbi as erc20 } from './rpc.mjs';

export const POOL = '0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2';
export const USDC = '0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48';
export const USDT = '0xdAC17F958D2ee523a2206206994597C13D831ec7';
export const AUSDC = '0x98C23E9d8f34FEFb1B7BD6a91B7FF122F4e16F5c';
export const AUSDT = '0x23878914EFE38d27C4D67Ab83ed1b93A74D4086a';
export const pool = parseAbi([
  'function supply(address,uint256,address,uint16)',
  'function deposit(address,uint256,address,uint16)',
  'function supplyWithPermit(address,uint256,address,uint16,uint256,uint8,bytes32,bytes32)',
  'function withdraw(address,uint256,address) returns (uint256)',
  'function getReserveData(address) view returns (uint256,uint128,uint128,uint128,uint128,uint128,uint40,uint16,address,address,address,address,uint128,uint128,uint128)',
  'function getReserveNormalizedIncome(address) view returns (uint256)',
]);

export const funding = {
  nativeBalance: 10n ** 19n,
  transfers: [
    { token: USDC, holder: '0x28C6c06298d514Db089934071355E5743bf21d60', amount: 10_000_000_000n },
    { token: USDT, holder: '0xF977814e90dA44bFA03b6295A0616a897441aceC', amount: 10_000_000_000n },
  ],
};

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

// Sequential reads: overlapping past-block reads can stall Anvil on one CPU.
export async function positions(url, owner, block = 'latest') {
  const result = {};
  for (const [name, token] of Object.entries({ usdc: USDC, usdt: USDT, ausdc: AUSDC, ausdt: AUSDT })) {
    result[name] = await balance(url, token, owner, block);
  }
  return result;
}

export function isWithdrawal(call) {
  if (call.to?.toLowerCase() !== POOL.toLowerCase()) return false;
  try { return decodeFunctionData({ abi: pool, data: call.data || call.input }).functionName === 'withdraw'; }
  catch { return false; }
}

// As Aave's ACL admin on the verifier's fork, set USDC's cap to its supply plus 5,000 USDC.
export async function lowerSupplyCap(url) {
  const provider = '0x2f39d218133AFaB8F2B819B1066c7E434Ad94E9e';
  const providerAbi = parseAbi([
    'function getACLAdmin() view returns (address)',
    'function getACLManager() view returns (address)',
    'function getPoolConfigurator() view returns (address)',
  ]);
  const address = raw => `0x${raw.slice(-40)}`;
  const admin = address(await read(url, provider, providerAbi, 'getACLAdmin'));
  const manager = address(await read(url, provider, providerAbi, 'getACLManager'));
  const configurator = address(await read(url, provider, providerAbi, 'getPoolConfigurator'));
  const adminRole = await read(url, manager, parseAbi(['function isPoolAdmin(address) view returns (bool)']), 'isPoolAdmin', [admin]);
  if (BigInt(adminRole) !== 1n) throw Object.assign(new Error('ACL admin does not hold the pool admin role'), { infrastructure: true });
  const previous = await reserve(url);
  const supplyCap = (previous.total + 999_999n) / 1_000_000n + 5000n;
  await rpc(url, 'anvil_setNextBlockBaseFeePerGas', ['0x0']);
  await rpc(url, 'anvil_impersonateAccount', [admin]);
  try {
    const hash = await rpc(url, 'eth_sendTransaction', [{ from: admin, to: configurator, gasPrice: '0x0', gas: '0x493e0',
      data: encodeFunctionData({ abi: parseAbi(['function setSupplyCap(address,uint256)']), functionName: 'setSupplyCap', args: [USDC, supplyCap] }) }]);
    if ((await receipt(url, hash)).status !== '0x1') throw Object.assign(new Error('Verifier supply-cap setup failed'), { infrastructure: true });
  } finally {
    await rpc(url, 'anvil_stopImpersonatingAccount', [admin]);
  }
  const market = await reserve(url);
  // Accrued treasury tokens leave less than 5,000 USDC of room.
  if (market.cap !== supplyCap * 1_000_000n || market.room < 100_000_000n || market.room > 5_000_000_000n) {
    throw Object.assign(new Error('Verifier supply cap does not match its fixture'), { infrastructure: true });
  }
  return { ...market, previousCap: previous.cap, admin, configurator };
}

export function requestedSupplies(requests) {
  const results = [];
  for (const request of requests) {
    const calls = ['eth_sendTransaction', 'wallet_sendTransaction'].includes(request.method) ? [request.params[0]] : request.method === 'wallet_sendCalls' ? request.params[0].calls : [];
    for (const call of calls) {
      if (call.to?.toLowerCase() !== POOL.toLowerCase()) continue;
      try {
        const decoded = decodeFunctionData({ abi: pool, data: call.data || call.input });
        if (['supply', 'deposit', 'supplyWithPermit'].includes(decoded.functionName)) results.push(decoded);
      } catch { /* Other Pool calls do not supply funds. */ }
    }
  }
  return results;
}
