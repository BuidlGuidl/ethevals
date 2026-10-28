import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { require, createPublicClient, http, parseAbi, encodeFunctionData, decodeEventLog, keccak256, zeroAddress } from './deps.mjs';
import { TOKENS, VIEW, ERC20, address } from './lib.mjs';
import { rpc as request, receipt } from './rpc.mjs';
const solc = require('solc');
const ROOT = path.dirname(fileURLToPath(import.meta.url));
const BLOCK = 26260992n;
export function createMarket({ url, output }) {
  const publicClient = createPublicClient({ transport: http(url, { timeout: 120_000 }) });
  const rpc = (method, params = []) => request(url, method, params);
  const call = (to, signature, args = []) => publicClient.readContract({ address: to, abi: parseAbi([signature]), functionName: signature.match(/function (\w+)/)[1], args });
  const save = (name, value) => fs.writeFileSync(path.join(output, name), JSON.stringify(value, (_, v) => typeof v === 'bigint' ? v.toString() : v, 2) + '\n');
  async function send(from, to, data, value = 0n) {
    const hash = await rpc('eth_sendTransaction', [{ from, ...(to ? { to } : {}), data, value: '0x' + value.toString(16), gasPrice: '0x0', gas: '0x1c9c380' }]);
    const result = await receipt(url, hash);
    if (result.status !== '0x1') throw new Error('Market transaction reverted: ' + hash);
    return { ...result, transactionHash: hash, blockNumber: BigInt(result.blockNumber) };
  }
  const HOLDER = {
    USDC: address('0x55FE002aefF02F77364de339a1292923A15844B8'),
    USDT: address('0xF977814e90dA44bFA03b6295A0616a897441aceC'),
  }
  const ANGSTROM = address('0x0000000aa232009084Bd71A5797d089AA4Edfad4')
  const ANGSTROM_ABI = parseAbi(['function execute(bytes encoded)'])
  let cachedAngstromNode
  async function angstromNode() {
    if (cachedAngstromNode) return cachedAngstromNode
    const data = encodeFunctionData({ abi: ANGSTROM_ABI, functionName: 'execute', args: ['0x'] })
    for (let n = BLOCK; n > BLOCK - 100n; n--) {
      const block = await rpc('eth_getBlockByNumber', ['0x' + n.toString(16), true])
      for (const tx of block.transactions.filter(tx => tx.to?.toLowerCase() === ANGSTROM.toLowerCase())) {
        try {
          await rpc('eth_call', [{ from: tx.from, to: ANGSTROM, data }, 'latest'])
          cachedAngstromNode = { address: tx.from, observedBlock: n.toString(), observedTransaction: tx.hash }
          return cachedAngstromNode
        } catch {}
      }
    }
    throw new Error('No active Angstrom node found in the last 100 pinned blocks.')
  }
  async function angstromSwap(account, data) {
    const node = await angstromNode()
    await rpc('anvil_setBalance', [node.address, '0x' + (10n ** 18n).toString(16)])
    await rpc('anvil_impersonateAccount', [node.address])
    const hashes = []
    await rpc('evm_setAutomine', [false])
    try {
      hashes.push(await rpc('eth_sendTransaction', [{ from: node.address, to: ANGSTROM,
        data: encodeFunctionData({ abi: ANGSTROM_ABI, functionName: 'execute', args: ['0x'] }), gas: '0xf4240' }]))
      hashes.push(await rpc('eth_sendTransaction', [{ from: account.owner, to: account.address, data, gas: '0x7a1200' }]))
      await rpc('evm_mine')
      const [unlock, swap] = await Promise.all(hashes.map(hash => publicClient.getTransactionReceipt({ hash })))
      if (unlock.status !== 'success' || swap.status !== 'success') throw new Error('Angstrom unlock or swap reverted.')
      if (unlock.blockNumber !== swap.blockNumber) throw new Error('Angstrom unlock and swap mined in different blocks.')
      return { receipt: swap, unlock: { ...node, transactionHash: unlock.transactionHash, block: unlock.blockNumber } }
    } catch (error) {
      for (const hash of hashes) await rpc('anvil_dropTransaction', [hash]).catch(() => {})
      throw error
    } finally {
      await rpc('evm_setAutomine', [true])
      await rpc('anvil_stopImpersonatingAccount', [node.address])
    }
  }
  async function slot(pool) {
    return pool.version === 3
      ? (await call(pool.address, 'function slot0() view returns (uint160,int24,uint16,uint16,uint16,uint8,bool)'))[0]
      : (await call(VIEW, 'function getSlot0(bytes32) view returns (uint160,int24,uint24,uint24)', [pool.id]))[0]
  }
  function ethPrice(pool, sqrt) {
    const eth0 = [zeroAddress.toLowerCase(), TOKENS.WETH.toLowerCase()].includes(pool.key.currency0.toLowerCase())
    const ratio = (Number(sqrt) / 2 ** 96) ** 2
    return eth0 ? ratio * 1e12 : 1e12 / ratio
  }
  function compileMover() {
    const source = fs.readFileSync(path.join(ROOT, 'MarketMover.sol'), 'utf8')
    const result = JSON.parse(solc.compile(JSON.stringify({
      language: 'Solidity', sources: { 'MarketMover.sol': { content: source } },
      settings: { optimizer: { enabled: true, runs: 200 }, evmVersion: 'cancun',
        outputSelection: { '*': { '*': ['abi', 'evm.bytecode.object'] } } },
    })))
    const errors = result.errors?.filter(e => e.severity === 'error')
    if (errors?.length) throw new Error(errors.map(e => e.formattedMessage).join('\n'))
    return result.contracts['MarketMover.sol'].MarketMover
  }
  async function mover() {
    const file = path.join(output, 'mover.json')
    if (fs.existsSync(file)) {
      const stored = JSON.parse(fs.readFileSync(file, 'utf8'))
      if (await rpc('eth_getCode', [stored.address, 'latest']) !== '0x') return stored
    }
    const owner = address('0x' + keccak256(Buffer.from('swaps-page-kit-market-mover')).slice(-40))
    await rpc('anvil_setBalance', [owner, '0x' + (10n ** 26n).toString(16)])
    await rpc('anvil_impersonateAccount', [owner])
    try {
      const compiled = compileMover()
      const receipt = await send(owner, null, '0x' + compiled.evm.bytecode.object)
      const deployed = receipt.contractAddress
      await rpc('anvil_setBalance', [deployed, '0x' + (10n ** 26n).toString(16)])
      await send(owner, TOKENS.WETH, encodeFunctionData({ abi: ERC20, functionName: 'deposit' }), 10n ** 25n)
      await send(owner, TOKENS.WETH, encodeFunctionData({ abi: ERC20, functionName: 'transfer', args: [deployed, 10n ** 25n] }))
      for (const symbol of ['USDC', 'USDT']) {
        const holder = HOLDER[symbol]
        const balance = await call(TOKENS[symbol], 'function balanceOf(address) view returns (uint256)', [holder])
        const amount = balance / 2n
        if (amount < 10_000_000n * 10n ** 6n) throw new Error(symbol + ' holder lacks market-move funds')
        await rpc('anvil_setBalance', [holder, '0x' + (10n ** 18n).toString(16)])
        await rpc('anvil_impersonateAccount', [holder])
        try { await send(holder, TOKENS[symbol], encodeFunctionData({ abi: ERC20, functionName: 'transfer', args: [deployed, amount] })) }
        finally { await rpc('anvil_stopImpersonatingAccount', [holder]) }
      }
      const result = { address: deployed, owner, abi: compiled.abi }
      save('mover.json', result)
      return result
    } finally { await rpc('anvil_stopImpersonatingAccount', [owner]) }
  }
  function sqrt(n) {
    if (n < 2n) return n
    let x = n, y = (x + 1n) / 2n
    while (y < x) { x = y; y = (x + n / x) / 2n }
    return x
  }
  async function moveMarket(pct, against) {
    if (!(pct > 0 && pct < 25)) throw new Error('Choose a percentage above 0 and below 25.')
    const { pools } = JSON.parse(fs.readFileSync(path.join(ROOT, 'pools.json'), 'utf8'))
    const account = await mover()
    const snapshot = await rpc('evm_snapshot')
    const scale = 1_000_000n
    const change = BigInt(Math.round(pct * 10000))
    const factor = against === 'eth-buyers' ? scale + change : scale - change
    const results = []
    await rpc('anvil_impersonateAccount', [account.owner])
    try {
      const ordered = [...pools.filter(p => p.key.hooks !== zeroAddress), ...pools.filter(p => p.key.hooks === zeroAddress)]
      for (const pool of ordered) {
        const before = await slot(pool)
        const eth0 = [zeroAddress.toLowerCase(), TOKENS.WETH.toLowerCase()].includes(pool.key.currency0.toLowerCase())
        const target = sqrt(before * before * (eth0 ? factor : scale) / (eth0 ? scale : factor))
        const zeroForOne = target < before
        const key = pool.key
        const data = encodeFunctionData({
          abi: account.abi, functionName: pool.version === 3 ? 'moveV3' : 'moveV4',
          args: [pool.version === 3 ? pool.address : key, zeroForOne, target],
        })
        const execution = pool.key.hooks.toLowerCase() === ANGSTROM.toLowerCase()
          ? await angstromSwap(account, data) : { receipt: await send(account.owner, account.address, data) }
        const { receipt } = execution
        const after = await slot(pool)
        const beforePrice = ethPrice(pool, before)
        const afterPrice = ethPrice(pool, after)
        const movedPct = (afterPrice / beforePrice - 1) * 100
        const event = receipt.logs.flatMap(log => {
          try {
            const decoded = decodeEventLog({ abi: account.abi, data: log.data, topics: log.topics })
            return decoded.eventName === 'Moved' ? [decoded.args] : []
          } catch { return [] }
        })[0]
        const result = { ...pool, beforeSqrtPriceX96: before, afterSqrtPriceX96: after,
          beforeEthPrice: beforePrice, afterEthPrice: afterPrice, movedPct,
          amount0: event?.amount0, amount1: event?.amount1, transactionHash: receipt.transactionHash,
          ...(execution.unlock ? { angstromUnlock: execution.unlock } : {}) }
        results.push(result)
        console.error('Moved v' + pool.version + ' ' + pool.stable + ' ' + (pool.address || pool.id) + ': ' + movedPct.toFixed(6) + '%')
        if (Math.abs(Math.abs(movedPct) - pct) > pct * .1) throw new Error('Pool missed the target: ' + (pool.address || pool.id))
      }
    } catch (error) {
      save('market-move-failure-' + Date.now() + '.json', { pct, against, results, error: error.message })
      if (!await rpc('evm_revert', [snapshot])) throw new Error('Market move failed and snapshot restoration failed: ' + error.message)
      throw new Error('Market move failed and restored its snapshot: ' + error.message)
    } finally { await rpc('anvil_stopImpersonatingAccount', [account.owner]) }
    const result = { pct, against, selection: 'Eight active v3 pools and three main hooked v4 pools at block 26260992',
      results }
    save('market-move-' + Date.now() + '.json', result)
    return result
  }

  return { moveMarket: async (...args) => {
    try { return await moveMarket(...args); }
    catch (error) { error.infrastructure = true; throw error; }
  } };
}
