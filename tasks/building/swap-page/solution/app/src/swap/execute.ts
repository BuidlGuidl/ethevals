import { type Address, type Hash, type Hex, encodeFunctionData } from 'viem'
import type { Config } from 'wagmi'
import {
  getPublicClient,
  sendTransaction,
  waitForTransactionReceipt,
} from 'wagmi/actions'

import {
  type Quote,
  type SwapResult,
  SWAP_ROUTER_02,
  buildSwapTx,
  erc20Abi,
  parseSwapReceipt,
} from './uniswap.ts'

const DEADLINE_SECONDS = 20n * 60n

export type SwapOutcome = {
  quote: Quote
  result: SwapResult
  hash: Hash
  gasCost: bigint
}

/**
 * Approves the router if needed, then sends the swap and reads the actual
 * amounts from its receipt. Throws if any step fails or is rejected.
 */
export async function executeSwap({
  config,
  chainId,
  quote,
  slippageBips,
  account,
  treasury,
  onProgress,
  onSubmitted,
}: {
  config: Config
  chainId: number
  quote: Quote
  slippageBips: bigint
  account: Address
  treasury: Address
  onProgress: (message: string) => void
  onSubmitted: (hash: Hash) => void
}): Promise<SwapOutcome> {
  const client = getPublicClient(config, { chainId })
  if (!client) throw new Error(`No RPC configured for chain ${chainId}`)

  const send = async (tx: { to: Address; data: Hex; value?: bigint }) => {
    const hash = await sendTransaction(config, { ...tx, chainId })
    return { hash, receipt: await waitForTransactionReceipt(config, { hash, chainId }) }
  }

  const { tokenIn } = quote
  if (tokenIn.address) {
    onProgress('Checking allowance…')
    const allowance = await client.readContract({
      address: tokenIn.address,
      abi: erc20Abi,
      functionName: 'allowance',
      args: [account, SWAP_ROUTER_02],
    })
    if (allowance < quote.amountIn) {
      // USDT reverts if you change a non-zero allowance to another non-zero value.
      if (allowance > 0n && tokenIn.symbol === 'USDT') {
        onProgress('USDT requires resetting your existing allowance to 0 first — confirm in your wallet')
        const { receipt } = await send(approveTx(tokenIn.address, 0n))
        if (receipt.status !== 'success') throw new Error('The allowance reset transaction reverted.')
      }
      onProgress(`Approve ${tokenIn.symbol} for the Uniswap router — confirm in your wallet`)
      const { receipt } = await send(approveTx(tokenIn.address, quote.amountIn))
      if (receipt.status !== 'success') throw new Error('The approval transaction reverted.')
    }
  }

  onProgress('Preparing swap…')
  const block = await client.getBlock()
  const tx = buildSwapTx({
    quote,
    slippageBips,
    account,
    treasury,
    deadline: block.timestamp + DEADLINE_SECONDS,
  })
  // Dry-run first so a doomed swap fails here, not after the user pays gas.
  await client.call({ account, ...tx })

  onProgress('Confirm the swap in your wallet')
  const hash = await sendTransaction(config, { ...tx, chainId })
  onSubmitted(hash)
  onProgress('Swap submitted — waiting for confirmation…')
  const receipt = await waitForTransactionReceipt(config, { hash, chainId })
  if (receipt.status !== 'success')
    throw new Error('The swap transaction reverted. Nothing was swapped; only gas was spent.')

  return {
    quote,
    result: parseSwapReceipt(receipt, quote.tokenIn, quote.tokenOut, account, treasury),
    hash,
    gasCost: receipt.gasUsed * receipt.effectiveGasPrice,
  }
}

function approveTx(token: Address, amount: bigint) {
  return {
    to: token,
    data: encodeFunctionData({
      abi: erc20Abi,
      functionName: 'approve',
      args: [SWAP_ROUTER_02, amount],
    }),
  }
}
