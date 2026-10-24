import {
  type Address,
  BaseError,
  type Hash,
  type Hex,
  ContractFunctionRevertedError,
  UserRejectedRequestError,
  maxUint256,
  encodeFunctionData,
} from 'viem'
import type { Config } from 'wagmi'
import {
  getConnection,
  getWalletClient,
  readContract,
  simulateContract,
  switchChain,
  waitForTransactionReceipt,
  writeContract,
} from 'wagmi/actions'

import { AAVE_POOL, SAVINGS_CHAIN_ID, type SavingsToken, erc20Abi, poolAbi, poolErrorMessages } from './aave.ts'

export type ProgressCallback = (message: string) => void

async function ensureSavingsChain(config: Config, onProgress: ProgressCallback) {
  if (getConnection(config).chainId === SAVINGS_CHAIN_ID) return
  onProgress('Switch your wallet to Ethereum…')
  await switchChain(config, { chainId: SAVINGS_CHAIN_ID })
}

/** Prompts the wallet via `submit` (which simulates first, surfacing reverts before signing) and waits for a successful receipt. */
async function confirm(label: string, config: Config, onProgress: ProgressCallback, submit: () => Promise<Hash>) {
  onProgress(`${label}: confirm in your wallet…`)
  const hash = await submit()
  onProgress(`${label}: waiting for confirmation…`)
  const receipt = await waitForTransactionReceipt(config, { hash, chainId: SAVINGS_CHAIN_ID })
  if (receipt.status !== 'success') throw new Error(`${label} transaction ${hash} reverted`)
  return receipt
}

export async function deposit(
  config: Config,
  { token, amount, account, onProgress }: { token: SavingsToken; amount: bigint; account: Address; onProgress: ProgressCallback },
) {
  await ensureSavingsChain(config, onProgress)

  const approve = (value: bigint) => async () => {
    const { request } = await simulateContract(config, {
      address: token.address,
      abi: erc20Abi,
      functionName: 'approve',
      args: [AAVE_POOL, value],
      account,
      chainId: SAVINGS_CHAIN_ID,
    })
    return writeContract(config, request)
  }

  // Read the allowance fresh rather than trusting the polled value.
  const allowance = await readContract(config, {
    address: token.address,
    abi: erc20Abi,
    functionName: 'allowance',
    args: [account, AAVE_POOL],
    chainId: SAVINGS_CHAIN_ID,
  })
  const wallet = await getWalletClient(config, { chainId: SAVINGS_CHAIN_ID })
  let atomic = false
  try {
    const capabilities = await wallet.getCapabilities({ account, chainId: SAVINGS_CHAIN_ID })
    atomic = capabilities.atomic?.status === 'supported'
  } catch {
    // Wallets without the calls API use individual transactions.
  }
  if (atomic) {
    const calls: { to: Address; data: Hex }[] = []
    if (allowance < amount) {
      if (token.requiresZeroAllowanceReset && allowance > 0n) {
        calls.push({ to: token.address, data: encodeFunctionData({ abi: erc20Abi, functionName: 'approve', args: [AAVE_POOL, 0n] }) })
      }
      calls.push({ to: token.address, data: encodeFunctionData({ abi: erc20Abi, functionName: 'approve', args: [AAVE_POOL, amount] }) })
    }
    calls.push({ to: AAVE_POOL, data: encodeFunctionData({ abi: poolAbi, functionName: 'supply', args: [token.address, amount, account, 0] }) })
    onProgress('Confirm the deposit in your wallet…')
    const { id } = await wallet.sendCalls({ account, calls, forceAtomic: true })
    onProgress('Waiting for the deposit…')
    const result = await wallet.waitForCallsStatus({ id })
    if (result.status !== 'success') throw new Error('The deposit failed. Your approval and deposit were reverted together.')
    return result
  }
  if (allowance < amount) {
    if (token.requiresZeroAllowanceReset && allowance > 0n) {
      await confirm(`Reset ${token.symbol} approval`, config, onProgress, approve(0n))
    }
    // Approve exactly the deposit amount rather than an unlimited allowance.
    await confirm(`Approve ${token.symbol}`, config, onProgress, approve(amount))
  }

  return confirm(`Deposit ${token.symbol}`, config, onProgress, async () => {
    const { request } = await simulateContract(config, {
      address: AAVE_POOL,
      abi: poolAbi,
      functionName: 'supply',
      args: [token.address, amount, account, 0],
      account,
      chainId: SAVINGS_CHAIN_ID,
    })
    return writeContract(config, request)
  })
}

export async function withdraw(
  config: Config,
  { token, amount, account, onProgress }: { token: SavingsToken; amount: bigint | 'max'; account: Address; onProgress: ProgressCallback },
) {
  await ensureSavingsChain(config, onProgress)

  return confirm(`Withdraw ${token.symbol}`, config, onProgress, async () => {
    const { request } = await simulateContract(config, {
      address: AAVE_POOL,
      abi: poolAbi,
      functionName: 'withdraw',
      // uint256 max tells Aave to withdraw the full balance at execution
      // time, including interest accrued between signing and mining.
      args: [token.address, amount === 'max' ? maxUint256 : amount, account],
      account,
      chainId: SAVINGS_CHAIN_ID,
    })
    return writeContract(config, request)
  })
}

export function describeError(error: unknown): string {
  if (error instanceof BaseError) {
    if (error.walk((e) => e instanceof UserRejectedRequestError)) return 'Transaction was rejected in your wallet.'
    const revert = error.walk((e) => e instanceof ContractFunctionRevertedError)
    if (revert instanceof ContractFunctionRevertedError) {
      const errorName = revert.data?.errorName
      if (errorName && errorName in poolErrorMessages) return poolErrorMessages[errorName]
      const reason = errorName ?? revert.reason
      return reason ? `Transaction would fail: ${reason}` : revert.shortMessage
    }
    return error.shortMessage
  }
  return error instanceof Error ? error.message : String(error)
}
