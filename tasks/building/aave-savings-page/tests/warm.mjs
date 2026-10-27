import { encodeFunctionData, parseAbi } from './deps.mjs';
import { POOL, USDC, USDT, AUSDC, AUSDT, pool, erc20, funding } from './chain.mjs';

const token = parseAbi(['function decimals() view returns (uint8)', 'function symbol() view returns (string)',
  'function scaledBalanceOf(address) view returns (uint256)', 'function scaledTotalSupply() view returns (uint256)']);
const MAX = 2n ** 256n - 1n;

// Cold reads can outlast rpc.mjs's 20-second limit on a slow upstream, and setup has no page waiting on it.
async function call(url, method, params) {
  let data;
  try {
    const response = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ jsonrpc: '2.0', id: 1, method, params }), signal: AbortSignal.timeout(180_000) });
    if (!response.ok) throw new Error(`Warm-up RPC HTTP ${response.status}`);
    data = await response.json();
  } catch (error) {
    error.infrastructure = true;
    throw error;
  }
  // A revert only leaves state cold. Anything else, such as a missing method, must stop setup.
  if (data.error && data.error.code !== 3 && !/revert/i.test(data.error.message)) {
    throw Object.assign(new Error(`Warm-up ${method} failed: ${data.error.message}`), { infrastructure: true });
  }
  return data.result;
}
const tx = (from, to, abi, functionName, args) => ({ from, to, data: encodeFunctionData({ abi, functionName, args }) });

// Runs before the first snapshot, so the forks keep everything fetched here.
// It reads what the pages read and simulates the journeys' deposits and withdrawals, without changing state.
export async function warmSavings(url) {
  for (const address of [USDC, USDT, AUSDC, AUSDT]) {
    for (const functionName of ['decimals', 'symbol']) await call(url, 'eth_call', [tx(undefined, address, token, functionName, []), 'latest']);
  }
  for (const [asset, aToken] of [[USDC, AUSDC], [USDT, AUSDT]]) {
    await call(url, 'eth_call', [tx(undefined, POOL, pool, 'getReserveData', [asset]), 'latest']);
    await call(url, 'eth_call', [tx(undefined, POOL, pool, 'getReserveNormalizedIncome', [asset]), 'latest']);
    await call(url, 'eth_call', [tx(undefined, aToken, token, 'scaledTotalSupply', []), 'latest']);
  }
  // The funding holders still hold both tokens, so each simulation can supply and withdraw for real.
  const [usdcHolder, usdtHolder] = funding.transfers.map(transfer => transfer.holder);
  const simulations = [
    [tx(usdcHolder, USDC, erc20, 'approve', [POOL, 100_000_000n]),
      tx(usdcHolder, POOL, pool, 'supply', [USDC, 100_000_000n, usdcHolder, 0]),
      tx(usdcHolder, POOL, pool, 'withdraw', [USDC, 40_000_000n, usdcHolder]),
      tx(usdcHolder, POOL, pool, 'withdraw', [USDC, MAX, usdcHolder])],
    [tx(usdtHolder, USDT, erc20, 'approve', [POOL, 100_000_000n]),
      tx(usdtHolder, POOL, pool, 'supply', [USDT, 100_000_000n, usdtHolder, 0])],
  ];
  for (const calls of simulations) {
    await call(url, 'eth_simulateV1', [{ blockStateCalls: [{ calls }], validation: false }, 'latest']);
  }
}
