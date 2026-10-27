import { encodeFunctionData, parseAbi } from './deps.mjs';
import { rpc, send } from './rpc.mjs';
const batch = parseAbi(['function execute((address to,uint256 value,bytes data)[] calls) payable']);
import { requireRead } from './rpc-policy.mjs';

export async function injectWallet(context, { account, mainRpc, atomic = false, beforeSend = async () => {} }) {
  const state = { requests: [], transactions: [], bundles: new Map(), pending: 0, lastActivity: Date.now() };
  await context.exposeBinding('__savingsWallet', async (_source, request) => {
    const { method, params = [] } = request;
    const entry = { method, params, time: Date.now() };
    state.requests.push(entry);
    state.pending++;
    const url = mainRpc;
    try {
      if (['eth_accounts', 'eth_requestAccounts'].includes(method)) return [account.address];
      if (method === 'eth_chainId') return '0x1';
      if (method === 'net_version') return '1';
      if (method === 'wallet_switchEthereumChain' || method === 'wallet_addEthereumChain') {
        const id = Number(params[0].chainId);
        if (id !== 1) throw Object.assign(new Error('Unknown chain'), { code: 4902 });
        return null;
      }
      if (method === 'wallet_requestPermissions' || method === 'wallet_getPermissions') return [{ parentCapability: 'eth_accounts', caveats: [] }];
      if (method === 'wallet_getCapabilities') return { '0x1': {
        atomic: { status: atomic ? 'supported' : 'unsupported' }, atomicBatch: { supported: atomic },
      } };
      if (method === 'wallet_revokePermissions') return null;
      if (method === 'eth_sendTransaction' || method === 'wallet_sendTransaction') {
        if (params[0].from && params[0].from.toLowerCase() !== account.address.toLowerCase()) throw new Error('Unknown sender');
        await beforeSend(params[0], entry);
        const result = await send(url, account, params[0]);
        state.transactions.push({ ...result, request: entry });
        entry.hash = result.hash;
        return result.hash;
      }
      if (method === 'wallet_sendCalls') {
        const bundle = params[0];
        if (Number(bundle.chainId) !== 1) throw new Error('Unknown bundle chain');
        if (!atomic && bundle.atomicRequired) throw Object.assign(new Error('Atomic calls unavailable'), { code: 5760 });
        if (bundle.from && bundle.from.toLowerCase() !== account.address.toLowerCase()) throw new Error('Unknown bundle sender');
        const calls = bundle.calls.map(call => ({ to: call.to, value: BigInt(call.value || 0), data: call.data || '0x' }));
        const results = [];
        if (atomic) {
          await beforeSend({ to: account.address, data: encodeFunctionData({ abi: batch, functionName: 'execute', args: [calls] }) }, entry);
          const result = await send(mainRpc, account, { to: account.address, data: encodeFunctionData({ abi: batch, functionName: 'execute', args: [calls] }) });
          results.push(result);
          state.transactions.push({ ...result, request: entry });
        } else {
          for (const call of calls) {
            await beforeSend(call, entry);
            const result = await send(mainRpc, account, call);
            results.push(result);
            state.transactions.push({ ...result, request: entry });
            if (result.receipt.status !== '0x1') break;
          }
        }
        const id = results[0].hash;
        state.bundles.set(id, { results, atomic });
        entry.hash = id;
        return bundle.version?.startsWith('1.') ? id : { id, capabilities: {} };
      }
      if (method === 'wallet_getCallsStatus') {
        const bundle = state.bundles.get(params[0]);
        if (!bundle) throw new Error('Unknown bundle');
        return { version: '2.0.0', id: params[0], chainId: '0x1', atomic: bundle.atomic,
          status: bundle.results.every(result => result.receipt.status === '0x1') ? 200 : 500,
          receipts: bundle.results.map(result => result.receipt), capabilities: {} };
      }
      if (method === 'wallet_showCallsStatus') return null;
      if (method === 'eth_signTypedData_v4' || method === 'eth_signTypedData') {
        const data = typeof params[1] === 'string' ? JSON.parse(params[1]) : params[1];
        return account.signTypedData(data);
      }
      if (method === 'personal_sign') return account.signMessage({ message: { raw: params[0] } });
      requireRead(method);
      return await rpc(url, method, params);
    } catch (error) {
      entry.error = error.shortMessage || error.message;
      return { __walletError: true, message: entry.error, code: error.code || -32603, data: error.data };
    } finally {
      state.pending--;
      state.lastActivity = Date.now();
    }
  });
  await context.addInitScript(({ address }) => {
    const listeners = new Map();
    const provider = {
      isMetaMask: true, isConnected: () => true, selectedAddress: address,
      chainId: '0x1', networkVersion: '1',
      on(event, listener) { if (!listeners.has(event)) listeners.set(event, new Set()); listeners.get(event).add(listener); return this; },
      removeListener(event, listener) { listeners.get(event)?.delete(listener); return this; },
      async request(request) {
        const result = await window.__savingsWallet(request);
        if (result?.__walletError) throw Object.assign(new Error(result.message), { code: result.code, data: result.data });
        return result;
      },
    };
    Object.defineProperty(window, 'ethereum', { value: provider, configurable: false });
    const announce = () => window.dispatchEvent(new CustomEvent('eip6963:announceProvider', { detail: Object.freeze({
      info: { uuid: 'e962621f-46e7-4a8c-a624-543c5f985230', name: 'Test Wallet', icon: 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg"/>', rdns: 'org.ethevals.wallet' }, provider,
    }) }));
    window.addEventListener('eip6963:requestProvider', announce);
    announce();
  }, { address: account.address });
  return state;
}
