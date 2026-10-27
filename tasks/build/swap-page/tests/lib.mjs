import path from 'node:path';
import { require, getAddress, zeroAddress, parseAbi } from './deps.mjs';
export { require } from './deps.mjs';
const urDir = path.dirname(require.resolve('@uniswap/universal-router-sdk'));
export const ur = {
  ...require('@uniswap/universal-router-sdk'),
  ...require(path.join(urDir, 'utils/constants.js')),
  ...require(path.join(urDir, 'utils/routerCommands.js')),
}
export const v4 = require('@uniswap/v4-sdk')
export const address = value => getAddress(value.toLowerCase())
export const TOKENS = {
  ETH: zeroAddress,
  WETH: address('0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2'),
  USDC: address('0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48'),
  USDT: address('0xdAC17F958D2ee523a2206206994597C13D831ec7'),
}
export const PERMIT2 = address('0x000000000022D473030F116dDEE9F6B43aC78BA3')
export const VIEW = address('0x7fFE42C4a5DEeA5b0feC41C94C136Cf115597227')
export const ROUTERS = {
  'V2 Router02': address('0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D'),
  ...Object.fromEntries(Object.entries(ur.CHAIN_CONFIGS[1].routerConfigs).map(([version, entry]) =>
    ['UniversalRouter ' + version, address(entry.address)])),
  'UniversalRouter legacy': address('0xEf1c6E67703c7BD7107eed8303Fbe6EC2554BF6B'),
  SwapRouter02: address('0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45'),
  SwapRouter: address('0xE592427A0AEce92De3Edee1F18E0157C05861564'),
}
export const ERC20 = parseAbi([
  'function balanceOf(address) view returns (uint256)',
  'function allowance(address,address) view returns (uint256)',
  'function approve(address spender,uint256 amount)',
  'function transfer(address to,uint256 amount)',
  'function deposit() payable',
  'function withdraw(uint256 amount)',
])
export const P2ABI = parseAbi([
  'function allowance(address,address,address) view returns (uint160 amount,uint48 expiration,uint48 nonce)',
  'function approve(address token,address spender,uint160 amount,uint48 expiration)',
  'function permit(address owner,((address token,uint160 amount,uint48 expiration,uint48 nonce) details,address spender,uint256 sigDeadline) permitSingle,bytes signature)',
  'function permit(address owner,((address token,uint160 amount,uint48 expiration,uint48 nonce)[] details,address spender,uint256 sigDeadline) permitBatch,bytes signature)',
  'function transferFrom(address from,address to,uint160 amount,address token)',
  'function transferFrom((address from,address to,uint160 amount,address token)[] transferDetails)',
])
export function label(value) {
  if (!value) return '<contract creation>'
  const name = Object.entries({ ...TOKENS, Permit2: PERMIT2, ...ROUTERS }).find(([, a]) => a.toLowerCase() === value.toLowerCase())?.[0]
  if (BigInt(value) === 1n) return value + ' (MSG_SENDER)'
  if (BigInt(value) === 2n) return value + ' (ADDRESS_THIS)'
  return name ? value + ' (' + name + ')' : value
}
