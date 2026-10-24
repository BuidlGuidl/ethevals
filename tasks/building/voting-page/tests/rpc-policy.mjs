// The task chain's allowed methods, excluding signed writes.
const reads = new Set([
  'eth_accounts', 'eth_blobBaseFee', 'eth_blockNumber', 'eth_call', 'eth_chainId', 'eth_config',
  'eth_createAccessList', 'eth_estimateGas', 'eth_feeHistory', 'eth_gasPrice', 'eth_getAccountInfo',
  'eth_getBalance', 'eth_getBlockByHash', 'eth_getBlockByNumber', 'eth_getBlockReceipts',
  'eth_getBlockTransactionCountByHash', 'eth_getBlockTransactionCountByNumber', 'eth_getCode',
  'eth_getFilterChanges', 'eth_getFilterLogs', 'eth_getLogs', 'eth_getProof', 'eth_getStorageAt',
  'eth_getTransactionByBlockHashAndIndex', 'eth_getTransactionByBlockNumberAndIndex',
  'eth_getTransactionByHash', 'eth_getTransactionCount', 'eth_getTransactionReceipt',
  'eth_maxPriorityFeePerGas', 'eth_newBlockFilter', 'eth_newFilter', 'eth_newPendingTransactionFilter',
  'eth_simulateV1', 'eth_syncing', 'eth_uninstallFilter', 'net_listening', 'net_version',
  'web3_clientVersion', 'web3_sha3',
]);

export function requireRead(method) {
  if (!reads.has(method)) throw Object.assign(new Error('RPC permits reads only'), { code: 4200 });
}

export const walletWrites = requests => requests.filter(({ method }) =>
  /^(?:eth_sendTransaction|wallet_sendTransaction|wallet_sendCalls|eth_sign.*|personal_sign)$/.test(method));

export async function walletIdle(wallet, { idleMs = 3000, timeoutMs = 20_000 } = {}) {
  const started = Date.now();
  do {
    if (!wallet.pending && Date.now() - Math.max(started, wallet.lastActivity) >= idleMs) return true;
    await new Promise(resolve => setTimeout(resolve, 100));
  } while (Date.now() - started < timeoutMs);
  return false;
}
