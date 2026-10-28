import { createPublicClient, http, parseAbi, encodeFunctionData, toEventSelector } from './deps.mjs';
import { TOKENS, ROUTERS, PERMIT2, ERC20, P2ABI } from './lib.mjs';
import { rpc, send } from './rpc.mjs';
import { decode } from './decode.mjs';

export { TOKENS, ROUTERS, PERMIT2 } from './lib.mjs';
export const funding = {
  nativeBalance: 10n ** 19n,
  transfers: [
    { token: TOKENS.USDC, holder: '0x28C6c06298d514Db089934071355E5743bf21d60', amount: 10_000_000_000n },
    { token: TOKENS.USDT, holder: '0xF977814e90dA44bFA03b6295A0616a897441aceC', amount: 10_000_000_000n },
  ],
};
export const swapTopics = [
  'Swap(address,uint256,uint256,uint256,uint256,address)',
  'Swap(address,address,int256,int256,uint160,uint128,int24)',
  'Swap(bytes32,address,int128,int128,uint160,uint128,int24,uint24)',
].map(toEventSelector);
const same = (a, b) => a?.toLowerCase() === b?.toLowerCase();
export const routerTransaction = tx => Object.values(ROUTERS).some(router => same(tx.to, router));
export const hasSwapLog = receipt => receipt?.logs?.some(log => swapTopics.includes(log.topics[0]));

export function classify(tx, treasury) {
  const decoded = decode(tx.data || tx.input || '0x', tx.to);
  if (routerTransaction(tx) || /^(?:execute|multicall|exactInput|exactOutput|swapExact|swap\w*ForExact)/.test(decoded.function)) return { kind: 'swap', decoded };
  if (decoded.function === 'approve') return { kind: 'approve', decoded };
  if (same(tx.to, PERMIT2) && decoded.function === 'permit') return { kind: 'permit', decoded };
  if (same(tx.to, treasury) && BigInt(tx.value || 0) > 0n) return { kind: 'fee', decoded };
  if (decoded.function === 'transfer' && same(decoded.to, treasury)) return { kind: 'fee', decoded };
  return { kind: 'other', decoded };
}

export function classifyRequest(request, treasury) {
  const { method, params = [] } = request;
  if (['eth_sendTransaction', 'wallet_sendTransaction'].includes(method)) return classify(params[0], treasury);
  if (method === 'wallet_sendCalls') return { kind: 'bundle', calls: params[0].calls.map(tx => classify(tx, treasury)) };
  if (/^eth_signTypedData/.test(method)) {
    try {
      const typed = typeof params[1] === 'string' ? JSON.parse(params[1]) : params[1];
      if (same(typed?.domain?.verifyingContract, PERMIT2)) return { kind: 'permit', typedData: typed };
    } catch { /* Preserve malformed signature requests in the wallet log. */ }
  }
  return { kind: 'other' };
}

export function observedSpenders(wallet, treasury) {
  const addresses = new Map();
  const add = value => {
    if (typeof value === 'string' && /^0x[0-9a-f]{40}$/i.test(value)) addresses.set(value.toLowerCase(), value);
  };
  const visit = value => {
    if (!value || typeof value !== 'object') return;
    add(value.spender);
    for (const child of Object.values(value)) if (child && typeof child === 'object') {
      if (Array.isArray(child)) child.forEach(visit);
      else visit(child);
    }
  };
  for (const request of wallet.requests) {
    const classification = classifyRequest(request, treasury);
    if (classification.kind === 'permit') visit(classification);
    const calls = request.method === 'wallet_sendCalls' ? request.params[0].calls
      : ['eth_sendTransaction', 'wallet_sendTransaction'].includes(request.method) ? [request.params[0]] : [];
    for (const tx of calls) {
      const item = classify(tx, treasury);
      if (item.kind === 'swap') add(tx.to);
      if (['approve', 'permit'].includes(item.kind)) visit(item.decoded);
      // Router commands can carry a Permit2 permit inside the swap calldata.
      if (item.kind === 'swap') visit(item.decoded);
    }
  }
  return [...addresses.values()];
}

export function chainReader(url, owner, treasury) {
  const client = createPublicClient({ transport: http(url, { timeout: 120_000 }) });
  async function balances(address, blockNumber) {
    return Object.fromEntries(await Promise.all(Object.entries(TOKENS).map(async ([symbol, token]) => [symbol,
      symbol === 'ETH' ? await client.getBalance({ address, blockNumber }) : await client.readContract({ address: token, abi: ERC20, functionName: 'balanceOf', args: [address], blockNumber }),
    ])));
  }
  async function state(spenders = [], blockNumber) {
    const routers = Object.entries(ROUTERS);
    for (const address of spenders) if (!routers.some(([, known]) => same(known, address))) routers.push([address, address]);
    const approvals = [['Permit2', PERMIT2], ...routers.filter(([, address]) => !same(address, PERMIT2))];
    const tokens = Object.entries(TOKENS).filter(([symbol]) => symbol !== 'ETH');
    const erc20Allowances = [];
    const permit2Allowances = [];
    for (const [symbol, token] of tokens) {
      for (const [name, spender] of approvals) {
        erc20Allowances.push({ token: symbol, spender: name, address: spender,
          amount: await client.readContract({ address: token, abi: ERC20, functionName: 'allowance', args: [owner, spender], blockNumber }) });
      }
      for (const [name, spender] of routers) {
        const [amount, expiration, nonce] = await client.readContract({ address: PERMIT2, abi: P2ABI, functionName: 'allowance', args: [owner, token, spender], blockNumber });
        permit2Allowances.push({ token: symbol, spender: name, address: spender, amount, expiration, nonce });
      }
    }
    const block = await client.getBlock({ blockNumber });
    return { owner, treasury, block: block.number, timestamp: block.timestamp,
      ownerBalances: await balances(owner, blockNumber), treasuryBalances: await balances(treasury, blockNumber),
      routerBalances: await Promise.all(routers.map(async ([name, address]) => ({ name, address, balances: await balances(address, blockNumber) }))),
      erc20Allowances, permit2Allowances };
  }
  async function transactions(wallet) {
    return Promise.all(wallet.transactions.map(async result => {
      const tx = await rpc(url, 'eth_getTransactionByHash', [result.hash]);
      const relevant = routerTransaction(tx) || hasSwapLog(result.receipt);
      let treasuryDelta;
      if (relevant) {
        const block = BigInt(result.receipt.blockNumber);
        const [before, after] = await Promise.all([balances(treasury, block - 1n), balances(treasury, block)]);
        treasuryDelta = Object.fromEntries(Object.keys(TOKENS).map(symbol => [symbol, after[symbol] - before[symbol]]));
      }
      return { ...result, tx, treasuryDelta, decoded: decode(tx.input || '0x', tx.to), kind: classify(tx, treasury).kind,
        relevant,
        gasCost: BigInt(result.receipt.gasUsed) * BigInt(result.receipt.effectiveGasPrice) };
    }));
  }
  async function seedUSDT(account, spender) {
      const result = await send(url, account, { to: TOKENS.USDT,
        data: encodeFunctionData({ abi: ERC20, functionName: 'approve', args: [spender, 1_000_000n] }) });
      if (result.receipt.status !== '0x1') throw Object.assign(new Error('USDT allowance fixture failed'), { infrastructure: true });
      const allowance = await client.readContract({ address: TOKENS.USDT, abi: ERC20, functionName: 'allowance', args: [account.address, spender] });
      if (allowance !== 1_000_000n) throw Object.assign(new Error('USDT allowance fixture differs from 1 USDT'), { infrastructure: true });
  }
  return { state, transactions, balances, seedUSDT };
}
