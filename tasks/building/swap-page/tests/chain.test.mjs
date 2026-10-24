import test from 'node:test';
import assert from 'node:assert/strict';
import net from 'node:net';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { chainReader } from './chain.mjs';
import { TOKENS, ROUTERS, PERMIT2 } from './lib.mjs';
import { require, encodeFunctionData, parseAbi } from './deps.mjs';
import { rpc, receipt } from './rpc.mjs';
import { until } from './harness.mjs';

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
            return spender == 0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D ? 1 : 0;
          }
        }
        contract Permit {
          function allowance(address,address,address) external pure returns (uint160,uint48,uint48) { return (0,0,0); }
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
  } finally {
    if (child.exitCode === null) { const exited = once(child, 'exit'); child.kill('SIGTERM'); await exited; }
  }
});
