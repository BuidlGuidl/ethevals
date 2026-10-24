import test from 'node:test';
import assert from 'node:assert/strict'
import { encodeFunctionData, encodeAbiParameters, parseAbiParameters } from './deps.mjs'
import { ur, v4, TOKENS, ROUTERS, PERMIT2, P2ABI } from './lib.mjs'
import { ABI, decode } from './decode.mjs'
import { classify, classifyRequest } from './chain.mjs'
import { finiteDeadline, sentMinimum, minimumCheck, belief } from './checks.mjs'

test('SDK and legacy calldata decode across router versions', () => {
const recipient = '0x0000000000000000000000000000000000000001'
const key = { currency0: TOKENS.ETH, currency1: TOKENS.USDC, fee: 500, tickSpacing: 10,
  hooks: TOKENS.ETH }
const results = []
for (const [name, router] of Object.entries(ROUTERS).filter(([name]) => name.startsWith('Universal'))) {
  const extended = /2\.1|2\.2/.test(name)
  const fields = extended ? ur.V2V3_SWAP_COMMANDS_V2_1_1[0].params : ur.COMMAND_DEFINITION[0].params
  const input = encodeAbiParameters(parseAbiParameters(fields.map(d => d.type + ' ' + d.name).join(',')),
    [recipient, 500000000n, 12345n, TOKENS.USDC + '0001f4' + TOKENS.WETH.slice(2), true,
      ...(extended ? [[0n]] : [])])
  for (const deadline of [undefined, 1234567890n]) {
    const abi = ABI.filter(f => f.name === 'execute' && f.inputs.length === (deadline ? 3 : 2))
    const data = encodeFunctionData({ abi, functionName: 'execute', args: ['0x00', [input], ...(deadline ? [deadline] : [])] })
    const result = decode(data, router)
    assert.equal(result.deadline, deadline ?? 'absent')
    assert.equal(result.commands[0].amountOutMin, 12345n)
    assert.equal(result.commands[0].recipient, recipient)
    results.push({ name, deadline: result.deadline, v3: true })
  }
  if (name.includes('legacy') || name.includes('1.2')) continue
  const planner4 = new v4.V4Planner()
  planner4.addAction(v4.Actions.SWAP_EXACT_IN_SINGLE, [{
    poolKey: key, zeroForOne: false, amountIn: '500000000', amountOutMinimum: '12345',
    ...(extended ? { minHopPriceX36: '0' } : {}), hookData: '0x',
  }], extended ? '2.1.1' : '2.0')
  planner4.addAction(v4.Actions.TAKE, [TOKENS.ETH, recipient, '0'])
  const data4 = encodeFunctionData({ abi: ABI, functionName: 'execute', args: ['0x10', [planner4.finalize()], 1234567890n] })
  const result4 = decode(data4, router)
  assert.equal(result4.commands[0].actions[0].swap.amountOutMinimum, 12345n)
  assert.equal(result4.commands[0].actions[1].recipient, recipient)
  results.push({ name, v4: true })
}
for (const old of [false, true]) {
  const exact = ABI.find(f => f.name === 'exactInputSingle' && f.inputs[0].components.some(c => c.name === 'deadline') === old)
  const params = { tokenIn: TOKENS.USDC, tokenOut: TOKENS.WETH, fee: 500, recipient,
    ...(old ? { deadline: 1234567890n } : {}), amountIn: 500000000n, amountOutMinimum: 12345n, sqrtPriceLimitX96: 0n }
  const inner = encodeFunctionData({ abi: [exact], functionName: 'exactInputSingle', args: [params] })
  const router = old ? ROUTERS.SwapRouter : ROUTERS.SwapRouter02
  for (const deadline of [undefined, 1234567890n]) {
    const multi = ABI.filter(f => f.name === 'multicall' && f.inputs.length === (deadline ? 2 : 1) && f.inputs[0].type !== 'bytes32')
    const data = encodeFunctionData({ abi: multi, functionName: 'multicall', args: [...(deadline ? [deadline] : []), [inner]] })
    const result = decode(data, router)
    assert.equal(result.calls[0].amountOutMinimum, 12345n)
    assert.equal(result.calls[0].deadline, old || deadline ? 1234567890n : 'absent')
    results.push({ name: old ? 'SwapRouter' : 'SwapRouter02', multicall: true, deadline: result.calls[0].deadline })
  }
}
const batch = { details: [{ token: TOKENS.USDC, amount: 5n, expiration: 12345, nonce: 0 }],
  spender: ROUTERS['UniversalRouter 2.0'], sigDeadline: 1234567890n }
const data = encodeFunctionData({ abi: P2ABI, functionName: 'permit', args: [recipient, batch, '0x1234'] })
assert.equal(decode(data, PERMIT2).permitBatch.details[0].amount, 5n)

console.log('Passed ' + (results.length + 1) + ' decoder cases.')

});

test('classifies and decodes every V2 Router02 function and SwapRouter02 v2 multicalls', () => {
  const timestamp = 1700000000n;
  for (const fn of ABI.filter(fn => fn.name?.startsWith('swap'))) {
    const direct = fn.inputs.some(input => input.name === 'deadline');
    const router = direct ? ROUTERS['V2 Router02'] : ROUTERS.SwapRouter02;
    const output = fn.name.includes('ForETH') || fn.name.includes('ForExactETH') ? TOKENS.WETH : TOKENS.USDC;
    const args = fn.inputs.map(input => ({ amountIn: 500000000n, amountOutMin: 200000000n, amountOut: 200000000n,
      amountInMax: 500000000n, path: [TOKENS.USDT, output], to: TOKENS.USDC, deadline: timestamp + 1200n })[input.name]);
    const inner = encodeFunctionData({ abi: [fn], functionName: fn.name, args });
    const data = direct ? inner : encodeFunctionData({ abi: ABI.filter(fn => fn.name === 'multicall' && fn.inputs[0].type === 'uint256'),
      functionName: 'multicall', args: [timestamp + 1200n, [inner]] });
    const decoded = decode(data, router);
    const symbol = output === TOKENS.WETH ? 'ETH' : 'USDC';
    assert.equal(classify({ to: router, data }).kind, 'swap', fn.name);
    assert.equal(classifyRequest({ method: 'eth_sendTransaction', params: [{ to: router, data }] }).kind, 'swap');
    assert.equal(finiteDeadline(decoded, timestamp), true, fn.name);
    assert.equal(sentMinimum(decoded, symbol), 200000000n, fn.name);
    if (!direct) assert.equal(finiteDeadline(decode(inner, router), timestamp), false);
  }
});

test('0x8000 cannot use an optional Universal Router swap to enforce the minimum', () => {
  const router = ROUTERS['UniversalRouter legacy'];
  const fields = ur.COMMAND_DEFINITION[0].params;
  const encode = minimum => encodeAbiParameters(parseAbiParameters(fields.map(field => field.type + ' ' + field.name).join(',')),
    ['0x0000000000000000000000000000000000000001', 500000000n, minimum, TOKENS.USDC + '0001f4' + TOKENS.WETH.slice(2), true]);
  const data = encodeFunctionData({ abi: ABI, functionName: 'execute', args: ['0x8000', [encode(200000000000000000n), encode(0n)], 1700001200n] });
  const decoded = decode(data, router);
  assert.deepEqual(decoded.commands.map(command => command.allowRevert), [true, false]);
  assert.equal(sentMinimum(decoded, 'ETH'), 0n);
  assert.equal(minimumCheck(belief('Minimum 0.2 ETH', 'ETH'), decoded, 'ETH', 210000000000000000n).passed, false);
  assert.equal(sentMinimum({ commands: [{ allowRevert: true, actions: [{ amountOutMinimum: 200000000000000000n }] }, { amountOutMin: 0n }] }, 'ETH'), 0n);
});
