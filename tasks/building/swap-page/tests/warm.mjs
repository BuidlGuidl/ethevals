import fs from 'node:fs/promises';
import { encodeFunctionData, parseAbi, parseUnits } from './deps.mjs';
import { TOKENS, ROUTERS } from './lib.mjs';
import { rpc } from './rpc.mjs';

export const journeys = {
  usdcEth: { name: 'usdc-eth', input: 'USDC', output: 'ETH', amount: '500' },
  ethUsdc: { name: 'eth-usdc', input: 'ETH', output: 'USDC', amount: '1' },
  usdtUsdc: { name: 'usdt-usdc', input: 'USDT', output: 'USDC', amount: '1000' },
  usdtSeeded: { name: 'usdt-seeded', input: 'USDT', output: 'USDC', amount: '1000' },
  drift: { name: 'drift', input: 'USDC', output: 'ETH', amount: '500', mode: 'drift' },
  moved: { name: 'moved', input: 'USDC', output: 'ETH', amount: '2000', mode: 'moved' },
  rejected: { name: 'rejected', input: 'USDC', output: 'ETH', amount: '500', mode: 'reject' },
  reverted: { name: 'reverted', input: 'USDC', output: 'ETH', amount: '500', mode: 'race' },
};

const v3Abi = parseAbi(['function quoteExactInputSingle((address tokenIn,address tokenOut,uint256 amountIn,uint24 fee,uint160 sqrtPriceLimitX96) params) returns (uint256,uint160,uint32,uint256)']);
const v4Abi = parseAbi(['function quoteExactInputSingle(((address currency0,address currency1,uint24 fee,int24 tickSpacing,address hooks) poolKey,bool zeroForOne,uint128 exactAmount,bytes hookData) params) returns (uint256,uint256)']);
const v2Abi = parseAbi(['function getAmountsOut(uint256 amountIn,address[] path) view returns (uint256[])']);

export async function warmQuotes(url) {
  const { pools } = JSON.parse(await fs.readFile(new URL('./pools.json', import.meta.url), 'utf8'));
  const unique = new Map(Object.values(journeys).map(journey => [`${journey.input}:${journey.output}:${journey.amount}`, journey]));
  async function quote(to, abi, functionName, args) {
    const data = encodeFunctionData({ abi, functionName, args });
    try { await rpc(url, 'eth_call', [{ to, data }, 'latest']); }
    catch (error) {
      // Missing pools and hook restrictions can revert. Transport failures must stop setup.
      if (error.code !== 3 && !/revert/i.test(error.message)) throw error;
    }
  }
  for (const { input, output, amount } of unique.values()) {
    const tokenIn = TOKENS[input === 'ETH' ? 'WETH' : input];
    const tokenOut = TOKENS[output === 'ETH' ? 'WETH' : output];
    const amountIn = parseUnits(amount, input === 'ETH' ? 18 : 6);
    for (const fee of [100, 500, 3000, 10000]) {
      await quote('0x61fFE014bA17989E743c5F6cB21bF9697530B21e', v3Abi, 'quoteExactInputSingle',
        [{ tokenIn, tokenOut, amountIn, fee, sqrtPriceLimitX96: 0n }]);
    }
    const matches = (currency, symbol) => currency.toLowerCase() === TOKENS[symbol].toLowerCase()
      || symbol === 'ETH' && currency.toLowerCase() === TOKENS.WETH.toLowerCase();
    for (const pool of pools.filter(pool => pool.version === 4)) {
      const { currency0, currency1 } = pool.key;
      const zeroForOne = matches(currency0, input) && matches(currency1, output);
      if (!zeroForOne && !(matches(currency1, input) && matches(currency0, output))) continue;
      await quote('0x99bd42b2b22e531f283b7f8a86dff631eb16a9d1', v4Abi, 'quoteExactInputSingle',
        [{ poolKey: pool.key, zeroForOne, exactAmount: amountIn, hookData: '0x' }]);
    }
    await quote(ROUTERS['V2 Router02'], v2Abi, 'getAmountsOut', [amountIn, [tokenIn, tokenOut]]);
  }
}
