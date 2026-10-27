import path from 'node:path'
import {
  parseAbi, parseAbiParameters, decodeAbiParameters, decodeFunctionData, toFunctionSelector,
} from './deps.mjs'
import { ur, v4, require, ERC20, P2ABI, PERMIT2, ROUTERS, label } from './lib.mjs'

const v4dir = path.dirname(require.resolve('@uniswap/v4-sdk'))
const v4defs = require(path.join(v4dir, 'utils/v4Planner.js'))
export const ABI = parseAbi([
  'function swapExactTokensForTokens(uint256 amountIn,uint256 amountOutMin,address[] path,address to,uint256 deadline) returns (uint256[])',
  'function swapTokensForExactTokens(uint256 amountOut,uint256 amountInMax,address[] path,address to,uint256 deadline) returns (uint256[])',
  'function swapExactETHForTokens(uint256 amountOutMin,address[] path,address to,uint256 deadline) payable returns (uint256[])',
  'function swapTokensForExactETH(uint256 amountOut,uint256 amountInMax,address[] path,address to,uint256 deadline) returns (uint256[])',
  'function swapExactTokensForETH(uint256 amountIn,uint256 amountOutMin,address[] path,address to,uint256 deadline) returns (uint256[])',
  'function swapETHForExactTokens(uint256 amountOut,address[] path,address to,uint256 deadline) payable returns (uint256[])',
  'function swapExactTokensForTokensSupportingFeeOnTransferTokens(uint256 amountIn,uint256 amountOutMin,address[] path,address to,uint256 deadline)',
  'function swapExactETHForTokensSupportingFeeOnTransferTokens(uint256 amountOutMin,address[] path,address to,uint256 deadline) payable',
  'function swapExactTokensForETHSupportingFeeOnTransferTokens(uint256 amountIn,uint256 amountOutMin,address[] path,address to,uint256 deadline)',
  'function swapExactTokensForTokens(uint256 amountIn,uint256 amountOutMin,address[] path,address to) payable returns (uint256)',
  'function swapTokensForExactTokens(uint256 amountOut,uint256 amountInMax,address[] path,address to) payable returns (uint256)',
  'function execute(bytes commands,bytes[] inputs,uint256 deadline) payable',
  'function execute(bytes commands,bytes[] inputs) payable',
  'function multicall(bytes[] data) payable returns (bytes[])',
  'function multicall(uint256 deadline,bytes[] data) payable returns (bytes[])',
  'function multicall(bytes32 previousBlockhash,bytes[] data) payable returns (bytes[])',
  'function exactInputSingle((address tokenIn,address tokenOut,uint24 fee,address recipient,uint256 amountIn,uint256 amountOutMinimum,uint160 sqrtPriceLimitX96) params) payable returns (uint256)',
  'function exactInputSingle((address tokenIn,address tokenOut,uint24 fee,address recipient,uint256 deadline,uint256 amountIn,uint256 amountOutMinimum,uint160 sqrtPriceLimitX96) params) payable returns (uint256)',
  'function exactInput((bytes path,address recipient,uint256 amountIn,uint256 amountOutMinimum) params) payable returns (uint256)',
  'function exactInput((bytes path,address recipient,uint256 deadline,uint256 amountIn,uint256 amountOutMinimum) params) payable returns (uint256)',
  'function exactOutputSingle((address tokenIn,address tokenOut,uint24 fee,address recipient,uint256 amountOut,uint256 amountInMaximum,uint160 sqrtPriceLimitX96) params) payable returns (uint256)',
  'function exactOutputSingle((address tokenIn,address tokenOut,uint24 fee,address recipient,uint256 deadline,uint256 amountOut,uint256 amountInMaximum,uint160 sqrtPriceLimitX96) params) payable returns (uint256)',
  'function exactOutput((bytes path,address recipient,uint256 amountOut,uint256 amountInMaximum) params) payable returns (uint256)',
  'function exactOutput((bytes path,address recipient,uint256 deadline,uint256 amountOut,uint256 amountInMaximum) params) payable returns (uint256)',
  'function unwrapWETH9(uint256 amountMinimum,address recipient) payable',
  'function unwrapWETH9WithFee(uint256 amountMinimum,address recipient,uint256 feeBips,address feeRecipient) payable',
  'function sweepToken(address token,uint256 amountMinimum,address recipient) payable',
  'function sweepTokenWithFee(address token,uint256 amountMinimum,address recipient,uint256 feeBips,address feeRecipient) payable',
  'function refundETH() payable',
])
const newer = to => Object.entries(ROUTERS).some(([name, a]) => /2\.1|2\.2/.test(name) && a.toLowerCase() === to?.toLowerCase())
const decodeFields = (defs, raw) => {
  const params = parseAbiParameters(defs.map(d => d.type + ' ' + d.name).join(','))
  const values = decodeAbiParameters(params, raw)
  return Object.fromEntries(defs.map((d, i) => [d.name, values[i]]))
}
export function v3path(raw, exactOut = false) {
  const data = raw.slice(2)
  const hops = []
  let token = '0x' + data.slice(0, 40)
  for (let i = 40; i + 46 <= data.length; i += 46) {
    const fee = Number.parseInt(data.slice(i, i + 6), 16)
    const next = '0x' + data.slice(i + 6, i + 46)
    hops.push(exactOut ? { tokenIn: next, fee, tokenOut: token } : { tokenIn: token, fee, tokenOut: next })
    token = next
  }
  return exactOut ? hops.reverse() : hops
}
function commands(bytes, inputs, to, deadline) {
  return [...Buffer.from(bytes.slice(2), 'hex')].map((byte, i) => {
    const id = byte & (to?.toLowerCase() === ROUTERS['UniversalRouter 2.2.0'].toLowerCase() ? 0x7f : 0x3f)
    const name = ur.CommandType[id] || 'UNKNOWN_COMMAND_' + id
    const raw = inputs[i]
    try {
      if (id === 16) {
        const [actions, params] = decodeAbiParameters(parseAbiParameters('bytes,bytes[]'), raw)
        return { command: name, allowRevert: !!(byte & 128), deadline, actions:
          [...Buffer.from(actions.slice(2), 'hex')].map((action, j) => {
            const defs = (newer(to) && v4defs.V4_SWAP_ACTIONS_V2_1_1[action]) || v4.V4_BASE_ACTIONS_ABI_DEFINITION[action]
            return defs ? { action: v4.Actions[action] || action, ...decodeFields(defs, params[j]),
              ...(action === v4.Actions.TAKE_ALL ? { recipient: 'MSG_SENDER (implicit)' } : {}),
              ...(action === v4.Actions.SETTLE_ALL ? { payerIsUser: true } : {}) }
              : { action, raw: params[j], error: 'Unknown v4 action' }
          }) }
      }
      const defs = (newer(to) && ur.V2V3_SWAP_COMMANDS_V2_1_1[id]) || ur.COMMAND_DEFINITION[id]
      if (!defs?.params) return { command: name, raw, error: 'No ABI for command' }
      const fields = decodeFields(defs.params, raw)
      if (id === 33) fields.children = commands(fields.commands, fields.inputs, to, deadline)
      if ([0, 1].includes(id)) fields.hops = v3path(fields.path, id === 1)
      if (typeof fields.recipient === 'string') fields.recipientLabel = label(fields.recipient)
      return { command: name, allowRevert: !!(byte & 128), deadline, ...fields }
    } catch (error) {
      return { command: name, raw, error: error.message }
    }
  })
}
export function decode(data, to, inheritedDeadline = 'absent') {
  let decoded
  try {
    decoded = decodeFunctionData({ abi: to?.toLowerCase() === PERMIT2.toLowerCase() ? P2ABI : [...ABI, ...ERC20], data })
  } catch {
    return { function: 'unknown', deadline: inheritedDeadline, raw: data }
  }
  const { functionName: name, args = [] } = decoded
  if (name === 'execute') {
    const deadline = args.length === 3 ? args[2] : inheritedDeadline
    return { function: name, deadline, commands: commands(args[0], args[1], to, deadline) }
  }
  if (name === 'multicall') {
    const deadline = args.length === 2 && typeof args[0] === 'bigint' ? args[0] : inheritedDeadline
    return { function: name, deadline, previousBlockhash: typeof args[0] === 'string' ? args[0] : undefined,
      calls: args.at(-1).map(child => decode(child, to, deadline)) }
  }
  if (name.startsWith('exact')) {
    const params = args[0]
    return { function: name, ...params, deadline: params.deadline ?? inheritedDeadline,
      ...(params.path ? { hops: v3path(params.path, name.startsWith('exactOutput')) } : {}) }
  }
  const definition = (to?.toLowerCase() === PERMIT2.toLowerCase() ? P2ABI : [...ABI, ...ERC20])
    .find(f => f.type === 'function' && toFunctionSelector(f) === data.slice(0, 10))
  const fields = Object.fromEntries(args.map((a, i) => [definition?.inputs[i]?.name || 'arg' + i, a]))
  return { function: name, deadline: inheritedDeadline, ...fields }
}
