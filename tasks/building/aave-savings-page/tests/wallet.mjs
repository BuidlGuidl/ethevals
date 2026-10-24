import { encodeFunctionData, decodeFunctionData } from './deps.mjs';
import { rpc, send, batch, pool, POOL } from './chain.mjs';

export async function injectWallet(context, { account, mainRpc, atomic = false }) {
  const state = { chainId: 1, requests: [], transactions: [], bundles: new Map(), pending: 0 };
  await context.exposeBinding('__savingsWallet', async (_source, request) => {
    const { method, params = [] } = request;
    const entry = { method, params, chainId: state.chainId, time: Date.now() };
    state.requests.push(entry);
    state.pending++;
    const url = mainRpc;
    try {
      if (['eth_accounts', 'eth_requestAccounts'].includes(method)) return [account.address];
      if (method === 'eth_chainId') return `0x${state.chainId.toString(16)}`;
      if (method === 'net_version') return String(state.chainId);
      if (method === 'wallet_switchEthereumChain' || method === 'wallet_addEthereumChain') {
        const id = Number(params[0].chainId);
        if (id !== 1) throw Object.assign(new Error('Unknown chain'), { code: 4902 });
        state.chainId = id;
        return null;
      }
      if (method === 'wallet_requestPermissions' || method === 'wallet_getPermissions') return [{ parentCapability: 'eth_accounts', caveats: [] }];
      if (method === 'wallet_getCapabilities') return { '0x1': { atomic: { status: atomic ? 'supported' : 'unsupported' } } };
      if (method === 'wallet_revokePermissions') return null;
      if (method === 'eth_sendTransaction') {
        if (params[0].from?.toLowerCase() !== account.address.toLowerCase()) throw new Error('Unknown sender');
        const result = await send(url, account, params[0], entry.chainId);
        state.transactions.push({ ...result, chainId: entry.chainId, request: entry });
        entry.hash = result.hash;
        return result.hash;
      }
      if (method === 'wallet_sendCalls') {
        const bundle = params[0];
        if (!atomic || state.chainId !== 1 || Number(bundle.chainId) !== 1) throw new Error('Atomic calls unavailable on this chain');
        if (bundle.from && bundle.from.toLowerCase() !== account.address.toLowerCase()) throw new Error('Unknown bundle sender');
        const calls = bundle.calls.map(call => ({ to: call.to, value: BigInt(call.value || 0), data: call.data || '0x' }));
        const result = await send(mainRpc, account, { to: account.address, data: encodeFunctionData({ abi: batch, functionName: 'execute', args: [calls] }) });
        state.transactions.push({ ...result, chainId: 1, request: entry });
        state.bundles.set(result.hash, result);
        entry.hash = result.hash;
        return bundle.version?.startsWith('1.') ? result.hash : { id: result.hash, capabilities: {} };
      }
      if (method === 'wallet_getCallsStatus') {
        const result = state.bundles.get(params[0]);
        if (!result) throw new Error('Unknown bundle');
        return { version: '2.0.0', id: params[0], chainId: '0x1', atomic: true,
          status: result.receipt.status === '0x1' ? 200 : 500, receipts: [result.receipt], capabilities: {} };
      }
      if (method === 'wallet_showCallsStatus') return null;
      if (method === 'eth_signTypedData_v4' || method === 'eth_signTypedData') {
        const data = typeof params[1] === 'string' ? JSON.parse(params[1]) : params[1];
        return account.signTypedData(data);
      }
      if (method === 'personal_sign') return account.signMessage({ message: { raw: params[0] } });
      if (/^(anvil_|evm_|eth_sign|eth_sendRaw)/.test(method)) throw new Error('Unsupported wallet method');
      return await rpc(url, method, params);
    } catch (error) {
      entry.error = error.shortMessage || error.message;
      return { __walletError: true, message: entry.error, code: error.code || -32603, data: error.data };
    } finally {
      state.pending--;
    }
  });
  await context.addInitScript(({ address, chainId }) => {
    const listeners = new Map();
    const provider = {
      isMetaMask: true, isConnected: () => true, selectedAddress: address,
      chainId: `0x${chainId.toString(16)}`, networkVersion: String(chainId),
      on(event, listener) { if (!listeners.has(event)) listeners.set(event, new Set()); listeners.get(event).add(listener); return this; },
      removeListener(event, listener) { listeners.get(event)?.delete(listener); return this; },
      async request(request) {
        const result = await window.__savingsWallet(request);
        if (result?.__walletError) throw Object.assign(new Error(result.message), { code: result.code, data: result.data });
        if (request.method === 'wallet_switchEthereumChain') {
          this.chainId = request.params[0].chainId;
          this.networkVersion = String(Number(this.chainId));
          for (const listener of listeners.get('chainChanged') || []) listener(this.chainId);
        }
        return result;
      },
    };
    Object.defineProperty(window, 'ethereum', { value: provider, configurable: false });
    const announce = () => window.dispatchEvent(new CustomEvent('eip6963:announceProvider', { detail: Object.freeze({
      info: { uuid: 'e962621f-46e7-4a8c-a624-543c5f985230', name: 'Test Wallet', icon: 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg"/>', rdns: 'org.ethevals.wallet' }, provider,
    }) }));
    window.addEventListener('eip6963:requestProvider', announce);
    announce();
  }, { address: account.address, chainId: 1 });
  return state;
}

export function requestedSupplies(requests) {
  const results = [];
  for (const request of requests) {
    const calls = request.method === 'eth_sendTransaction' ? [request.params[0]] : request.method === 'wallet_sendCalls' ? request.params[0].calls : [];
    for (const call of calls) {
      if (call.to?.toLowerCase() !== POOL.toLowerCase()) continue;
      try {
        const decoded = decodeFunctionData({ abi: pool, data: call.data || call.input });
        if (['supply', 'supplyWithPermit'].includes(decoded.functionName)) results.push({ ...decoded, chainId: request.chainId });
      } catch { /* Other Pool calls do not supply funds. */ }
    }
  }
  return results;
}
