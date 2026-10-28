import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import net from 'node:net';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { chainReader, observedSpenders } from './chain.mjs';
import { TOKENS, ROUTERS, PERMIT2, ERC20, P2ABI } from './lib.mjs';
import { allowancesEmpty, routersEmpty } from './checks.mjs';
import { require, encodeFunctionData, parseAbi } from './deps.mjs';
import { rpc, receipt } from './rpc.mjs';
import { until } from './harness.mjs';

test('discovers approval, Permit2, bundled, failed, and swap destinations from wallet requests', () => {
  const addresses = Array.from({ length: 7 }, (_, i) => `0x${String(i + 3).repeat(40)}`);
  const [erc20, permit, batch, approve, swap, bundled, token] = addresses;
  const permitSingle = { details: { token: TOKENS.USDC, amount: 1n, expiration: 999n, nonce: 0n }, spender: permit, sigDeadline: 999n };
  const tx = (to, data) => ({ method: 'eth_sendTransaction', params: [{ to, data }] });
  const wallet = { requests: [
    { ...tx(TOKENS.USDC, encodeFunctionData({ abi: ERC20, functionName: 'approve', args: [erc20, 1n] })), error: 'rejected' },
    tx(PERMIT2, encodeFunctionData({ abi: P2ABI, functionName: 'permit', args: [token, permitSingle, '0x'] })),
    { method: 'eth_signTypedData_v4', params: [token, JSON.stringify({ domain: { verifyingContract: PERMIT2 }, message: { ...permitSingle, spender: batch } }, (_, value) => typeof value === 'bigint' ? String(value) : value)] },
    tx(PERMIT2, encodeFunctionData({ abi: P2ABI, functionName: 'approve', args: [TOKENS.USDC, approve, 1n, 999] })),
    tx(swap, encodeFunctionData({ abi: parseAbi(['function multicall(bytes[] data)']), functionName: 'multicall', args: [[]] })),
    { method: 'wallet_sendCalls', params: [{ calls: [{ to: TOKENS.USDT, data: encodeFunctionData({ abi: ERC20, functionName: 'approve', args: [bundled, 1n] }) }] }] },
    { method: 'eth_signTypedData_v4', params: [token, '{broken'] },
    tx(TOKENS.USDC, encodeFunctionData({ abi: ERC20, functionName: 'transfer', args: [token, 1n] })),
  ] };
  assert.deepEqual(observedSpenders(wallet, token).map(address => address.toLowerCase()).sort(), addresses.slice(0, 6).sort());
});

test('observes token and native cuts only in the swap block', { timeout: 30_000 }, async () => {
  const listener = net.createServer();
  await new Promise(resolve => listener.listen(0, '127.0.0.1', resolve));
  const port = listener.address().port;
  await new Promise(resolve => listener.close(resolve));
  const url = `http://127.0.0.1:${port}`;
  const child = spawn('anvil', ['--port', String(port), '--accounts', '0', '--chain-id', '1', '--base-fee', '0', '--silent'], { stdio: 'ignore' });
  try {
    assert.equal(await until(async () => await rpc(url, 'eth_chainId') === '0x1'), true);
    const compiled = JSON.parse(require('solc').compile(JSON.stringify({ language: 'Solidity',
      sources: { 'Fixture.sol': { content: `pragma solidity ^0.8.0;
        contract Token {
          mapping(address => uint) public balanceOf;
          function mint(address to, uint amount) external { balanceOf[to] += amount; }
          function allowance(address, address spender) external pure returns (uint) {
            return spender == 0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D ? 1 : spender == address(0x3333) ? type(uint).max : 0;
          }
        }
        contract Permit {
          function allowance(address,address,address spender) external pure returns (uint160,uint48,uint48) {
            return spender == address(0x3333) ? (uint160(5), type(uint48).max, uint48(0)) : (uint160(0), uint48(0), uint48(0));
          }
        }
        contract Router {
          function cut(address token, address payable to, uint amount) external payable {
            Token(token).mint(to, amount);
            (bool ok,) = to.call{value: msg.value}(""); require(ok);
          }
        }` } }, settings: { outputSelection: { '*': { '*': ['evm.deployedBytecode.object'] } } } })));
    const code = name => '0x' + compiled.contracts['Fixture.sol'][name].evm.deployedBytecode.object;
    for (const [symbol, address] of Object.entries(TOKENS)) if (symbol !== 'ETH') await rpc(url, 'anvil_setCode', [address, code('Token')]);
    await rpc(url, 'anvil_setCode', [PERMIT2, code('Permit')]);
    await rpc(url, 'anvil_setCode', [ROUTERS['V2 Router02'], code('Router')]);
    const owner = '0x1111111111111111111111111111111111111111';
    const treasury = '0x2222222222222222222222222222222222222222';
    await rpc(url, 'anvil_setBalance', [owner, '0x100000']);
    await rpc(url, 'anvil_impersonateAccount', [owner]);
    const transact = async tx => {
      const hash = await rpc(url, 'eth_sendTransaction', [{ from: owner, gasPrice: '0x0', gas: '0xf4240', ...tx }]);
      const mined = await receipt(url, hash);
      assert.equal(mined.status, '0x1');
      return { hash, receipt: mined };
    };
    const mint = amount => transact({ to: TOKENS.USDC, data: encodeFunctionData({ abi: parseAbi(['function mint(address to,uint256 amount)']), functionName: 'mint', args: [treasury, amount] }) });
    await transact({ to: treasury, value: '0x5' });
    await mint(7n);
    const swap = await transact({ to: ROUTERS['V2 Router02'], value: '0xb', data: encodeFunctionData({ abi: parseAbi(['function cut(address token,address to,uint256 amount) payable']),
      functionName: 'cut', args: [TOKENS.USDC, treasury, 13n] }) });
    await mint(17n);
    await transact({ to: treasury, value: '0x13' });
    const reader = chainReader(url, owner, treasury);
    const [observed] = await reader.transactions({ transactions: [swap] });
    assert.equal(observed.relevant, true);
    assert.deepEqual(observed.treasuryDelta, { ETH: 11n, WETH: 0n, USDC: 13n, USDT: 0n });
    const state = await reader.state();
    assert.deepEqual(state.erc20Allowances.filter(item => item.spender === 'V2 Router02').map(item => item.amount), [1n, 1n, 1n]);
    assert.equal(state.permit2Allowances.filter(item => item.spender === 'V2 Router02').length, 3);
    assert.equal(state.routerBalances.find(item => item.name === 'V2 Router02').address, ROUTERS['V2 Router02']);
    const custom = '0x0000000000000000000000000000000000003333';
    const baseline = await reader.state([custom, custom]);
    const expanded = await reader.state([custom], baseline.block);
    assert.equal(expanded.routerBalances.filter(item => item.address === custom).length, 1);
    assert.equal(expanded.erc20Allowances.filter(item => item.address === custom && item.amount === (1n << 256n) - 1n).length, 3);
    assert.equal(expanded.permit2Allowances.filter(item => item.address === custom && item.amount === 5n).length, 3);
    assert.equal(allowancesEmpty({ ...expanded, erc20Allowances: expanded.erc20Allowances.filter(item => item.address === custom) }), false);
    assert.equal(allowancesEmpty({ ...expanded, erc20Allowances: [] }), false);
    await transact({ to: TOKENS.USDC, data: encodeFunctionData({ abi: parseAbi(['function mint(address to,uint256 amount)']), functionName: 'mint', args: [custom, 1n] }) });
    assert.equal(routersEmpty(expanded, await reader.state([custom])), false);
    assert.equal(routersEmpty(expanded, await reader.state([custom], baseline.block)), true);
  } finally {
    if (child.exitCode === null) { const exited = once(child, 'exit'); child.kill('SIGTERM'); await exited; }
  }
});

test('waits out fork reads slower than viem\'s ten-second default', { timeout: 90_000 }, async () => {
  const listener = net.createServer();
  await new Promise(resolve => listener.listen(0, '127.0.0.1', resolve));
  const port = listener.address().port;
  await new Promise(resolve => listener.close(resolve));
  const url = `http://127.0.0.1:${port}`;
  const child = spawn('anvil', ['--port', String(port), '--accounts', '0', '--chain-id', '1', '--base-fee', '0', '--silent'], { stdio: 'ignore' });
  // Every read through this proxy takes 11 seconds, like a fork loading mainnet state under load.
  const proxy = http.createServer(async (request, response) => {
    const chunks = [];
    for await (const chunk of request) chunks.push(chunk);
    await new Promise(resolve => setTimeout(resolve, 11_000));
    const upstream = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: Buffer.concat(chunks) });
    response.writeHead(upstream.status, { 'Content-Type': 'application/json' }).end(await upstream.text());
  });
  await new Promise(resolve => proxy.listen(0, '127.0.0.1', resolve));
  try {
    assert.equal(await until(async () => await rpc(url, 'eth_chainId') === '0x1'), true);
    const compiled = JSON.parse(require('solc').compile(JSON.stringify({ language: 'Solidity',
      sources: { 'Token.sol': { content: 'pragma solidity ^0.8.0; contract Token { mapping(address => uint) public balanceOf; }' } },
      settings: { outputSelection: { '*': { '*': ['evm.deployedBytecode.object'] } } } })));
    const code = '0x' + compiled.contracts['Token.sol'].Token.evm.deployedBytecode.object;
    for (const [symbol, address] of Object.entries(TOKENS)) if (symbol !== 'ETH') await rpc(url, 'anvil_setCode', [address, code]);
    const owner = '0x1111111111111111111111111111111111111111';
    const treasury = '0x2222222222222222222222222222222222222222';
    await rpc(url, 'anvil_setBalance', [owner, '0x100000']);
    await rpc(url, 'anvil_impersonateAccount', [owner]);
    const hash = await rpc(url, 'eth_sendTransaction', [{ from: owner, to: ROUTERS['V2 Router02'], value: '0x1', gasPrice: '0x0', gas: '0x5208' }]);
    const mined = await receipt(url, hash);
    const reader = chainReader(`http://127.0.0.1:${proxy.address().port}`, owner, treasury);
    const [observed] = await reader.transactions({ transactions: [{ hash, receipt: mined }] });
    assert.equal(observed.relevant, true);
    assert.deepEqual(observed.treasuryDelta, { ETH: 0n, WETH: 0n, USDC: 0n, USDT: 0n });
  } finally {
    await new Promise(resolve => proxy.close(resolve));
    if (child.exitCode === null) { const exited = once(child, 'exit'); child.kill('SIGTERM'); await exited; }
  }
});
