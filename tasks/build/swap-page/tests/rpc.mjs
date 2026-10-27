import { createWalletClient, defineChain, http, encodeFunctionData, parseAbi, toHex } from './deps.mjs';

export const tokenAbi = parseAbi([
  'function balanceOf(address) view returns (uint256)',
  'function totalSupply() view returns (uint256)',
  'function allowance(address,address) view returns (uint256)',
  'function approve(address,uint256)', 'function transfer(address,uint256)',
]);
export async function rpc(url, method, params = []) {
  let data;
  try {
    const response = await fetch(url, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ jsonrpc: '2.0', id: 1, method, params }),
    signal: AbortSignal.timeout(120_000),
  });
    if (!response.ok) throw new Error(`Verifier RPC HTTP ${response.status}`);
    data = await response.json();
  } catch (error) {
    error.infrastructure = true;
    throw error;
  }
  if (data.error) {
    const error = new Error(data.error.message);
    Object.assign(error, { code: data.error.code, data: data.error.data, infrastructure: true });
    throw error;
  }
  return data.result;
}

export async function read(url, address, abi, functionName, args = []) {
  return rpc(url, 'eth_call', [{ to: address, data: encodeFunctionData({ abi, functionName, args }) }, 'latest']);
}
export const balance = async (url, token, owner) => BigInt(await read(url, token, tokenAbi, 'balanceOf', [owner]));

export async function receipt(url, hash) {
  const deadline = Date.now() + 120_000;
  do {
    const result = await rpc(url, 'eth_getTransactionReceipt', [hash]);
    if (result) return result;
    await new Promise(resolve => setTimeout(resolve, 100));
  } while (Date.now() < deadline);
  throw Object.assign(new Error(`No receipt for ${hash}`), { infrastructure: true });
}

export async function send(url, account, tx) {
  const chain = defineChain({ id: 1, name: 'Test chain', nativeCurrency: { name: 'Ether', symbol: 'ETH', decimals: 18 }, rpcUrls: { default: { http: [url] } } });
  const client = createWalletClient({ account, chain, transport: http(url) });
  const hash = await client.sendTransaction({
    to: tx.to, data: tx.data || tx.input || '0x', value: BigInt(tx.value || 0),
    gas: tx.gas ? BigInt(tx.gas) : 3_000_000n,
    gasPrice: 0n, type: 'legacy',
  });
  const mined = await receipt(url, hash);
  return { hash, receipt: mined };
}

export async function fundWallet(url, account, { nativeBalance, transfers }) {
  await rpc(url, 'anvil_setBalance', [account.address, toHex(nativeBalance)]);
  for (const { token, holder, amount } of transfers) {
    await rpc(url, 'anvil_impersonateAccount', [holder]);
    try {
      const hash = await rpc(url, 'eth_sendTransaction', [{ from: holder, to: token, gasPrice: '0x0', gas: '0x493e0',
        data: encodeFunctionData({ abi: tokenAbi, functionName: 'transfer', args: [account.address, amount] }) }]);
      if ((await receipt(url, hash)).status !== '0x1') throw new Error('Token funding failed');
    } finally {
      await rpc(url, 'anvil_stopImpersonatingAccount', [holder]);
    }
    if (await balance(url, token, account.address) !== amount) throw new Error('Test wallet funding mismatch');
  }
}
