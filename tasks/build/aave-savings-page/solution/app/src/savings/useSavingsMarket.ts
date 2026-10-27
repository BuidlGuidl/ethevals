import { type Address, zeroAddress } from 'viem'
import { useReadContracts } from 'wagmi'

import {
  AAVE_POOL,
  SAVINGS_CHAIN_ID,
  type ReserveStatus,
  type SavingsToken,
  decodeReserveConfiguration,
  erc20Abi,
  liquidityRateToApy,
  poolAbi,
  totalSuppliedForCap,
} from './aave.ts'

export type SavingsMarket = {
  apy: number
  status: ReserveStatus
  /** Underlying held by the aToken, i.e. the most that can be withdrawn right now. */
  availableLiquidity: bigint
  /** Remaining room under the supply cap, or null when uncapped. */
  remainingSupplyCap: bigint | null
  user?: {
    walletBalance: bigint
    /** aToken balance: principal plus all interest accrued so far. */
    deposited: bigint
    allowance: bigint
  }
}

// Roughly one mainnet block, so the deposited balance visibly accrues.
const REFRESH_MS = 12_000

export function useSavingsMarket(token: SavingsToken, account?: Address) {
  const owner = account ?? zeroAddress
  const query = useReadContracts({
    allowFailure: false,
    contracts: [
      { address: AAVE_POOL, abi: poolAbi, functionName: 'getReserveData', args: [token.address], chainId: SAVINGS_CHAIN_ID },
      { address: AAVE_POOL, abi: poolAbi, functionName: 'getReserveNormalizedIncome', args: [token.address], chainId: SAVINGS_CHAIN_ID },
      { address: token.aToken, abi: erc20Abi, functionName: 'totalSupply', chainId: SAVINGS_CHAIN_ID },
      { address: token.address, abi: erc20Abi, functionName: 'balanceOf', args: [token.aToken], chainId: SAVINGS_CHAIN_ID },
      { address: token.address, abi: erc20Abi, functionName: 'balanceOf', args: [owner], chainId: SAVINGS_CHAIN_ID },
      { address: token.aToken, abi: erc20Abi, functionName: 'balanceOf', args: [owner], chainId: SAVINGS_CHAIN_ID },
      { address: token.address, abi: erc20Abi, functionName: 'allowance', args: [owner, AAVE_POOL], chainId: SAVINGS_CHAIN_ID },
    ],
    query: {
      refetchInterval: REFRESH_MS,
      select: ([reserve, normalizedIncome, aTokenSupply, liquidity, walletBalance, deposited, allowance]): SavingsMarket => {
        const status = decodeReserveConfiguration(reserve.configuration, token.decimals)
        const supplied = totalSuppliedForCap(aTokenSupply, reserve.accruedToTreasury, normalizedIncome)
        return {
          apy: liquidityRateToApy(reserve.currentLiquidityRate),
          status,
          availableLiquidity: liquidity,
          remainingSupplyCap:
            status.supplyCap === null
              ? null
              : status.supplyCap > supplied
                ? status.supplyCap - supplied
                : 0n,
          user: account ? { walletBalance, deposited, allowance } : undefined,
        }
      },
    },
  })
  return query
}
