import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { chromium, privateKeyToAccount, generatePrivateKey, encodeFunctionData } from './deps.mjs';
import { injectWallet } from './wallet.mjs';
import { executedCalls, votesAbi } from './chain.mjs';

test('wallet_sendCalls records each executed deposit with its receipt', async () => {
  const server = http.createServer(async (request, response) => {
    let body = '';
    for await (const chunk of request) body += chunk;
    const payload = JSON.parse(body);
    const results = { eth_chainId: '0x7a69', eth_gasPrice: '0x1', eth_getTransactionCount: '0x0',
      eth_sendRawTransaction: '0x' + '12'.repeat(32), eth_getTransactionReceipt: { status: '0x1', logs: [] } };
    response.setHeader('content-type', 'application/json');
    response.end(JSON.stringify({ jsonrpc: '2.0', id: payload.id, result: results[payload.method] }));
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
  try {
    const context = await browser.newContext();
    const account = privateKeyToAccount(generatePrivateKey());
    const wallet = await injectWallet(context, { account, mainRpc: `http://127.0.0.1:${server.address().port}` });
    const page = await context.newPage();
    await page.goto('about:blank');
    const to = '0x0000000000000000000000000000000000000001';
    const call = { to, data: encodeFunctionData({ abi: votesAbi, functionName: 'depositFor', args: [account.address, 1000n] }) };
    await page.evaluate(call => window.ethereum.request({ method: 'wallet_sendCalls', params: [{ chainId: '0x7a69', version: '2.0.0', calls: [call] }] }), call);
    assert.deepEqual(wallet.transactions.map(tx => ({ call: tx.call, status: tx.receipt.status })), [{ call: { ...call, value: 0n }, status: '0x1' }]);
    assert.deepEqual(executedCalls(wallet, to, votesAbi, 'depositFor').map(tx => tx.args), [[account.address, 1000n]]);
  } finally {
    await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
});
