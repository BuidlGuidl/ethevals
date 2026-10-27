import { type Address, parseAbi } from 'viem'
import { mainnet } from 'wagmi/chains'

// Aave v3 "Ethereum" (core) market. Addresses verified against the chain in
// chain_context.json: PoolAddressesProvider.getPool() returns POOL, and
// Pool.getReserveData(token).aTokenAddress returns each aToken below.
export const SAVINGS_CHAIN_ID = mainnet.id
export const AAVE_POOL: Address = '0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2'

export type SavingsToken = {
  symbol: 'USDC' | 'USDT'
  address: Address
  aToken: Address
  decimals: number
  // USDT's approve() reverts when changing a non-zero allowance to another
  // non-zero value, so the allowance must be reset to 0 first.
  requiresZeroAllowanceReset: boolean
}

export const SAVINGS_TOKENS: readonly SavingsToken[] = [
  {
    symbol: 'USDC',
    address: '0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48',
    aToken: '0x98C23E9d8f34FEFb1B7BD6a91B7FF122F4e16F5c',
    decimals: 6,
    requiresZeroAllowanceReset: false,
  },
  {
    symbol: 'USDT',
    address: '0xdAC17F958D2ee523a2206206994597C13D831ec7',
    aToken: '0x23878914EFE38d27C4D67Ab83ed1b93A74D4086a',
    decimals: 6,
    requiresZeroAllowanceReset: true,
  },
]

export const poolAbi = parseAbi([
  'struct ReserveData { uint256 configuration; uint128 liquidityIndex; uint128 currentLiquidityRate; uint128 variableBorrowIndex; uint128 currentVariableBorrowRate; uint128 currentStableBorrowRate; uint40 lastUpdateTimestamp; uint16 id; address aTokenAddress; address stableDebtTokenAddress; address variableDebtTokenAddress; address interestRateStrategyAddress; uint128 accruedToTreasury; uint128 unbacked; uint128 isolationModeTotalDebt; }',
  'function getReserveData(address asset) view returns (ReserveData)',
  'function getReserveNormalizedIncome(address asset) view returns (uint256)',
  'function supply(address asset, uint256 amount, address onBehalfOf, uint16 referralCode)',
  'function withdraw(address asset, uint256 amount, address to) returns (uint256)',
  // Custom errors the Pool can raise for supply/withdraw, so reverts decode to names.
  'error InvalidAmount()',
  'error ReserveInactive()',
  'error ReserveFrozen()',
  'error ReservePaused()',
  'error SupplyCapExceeded()',
  'error NotEnoughAvailableUserBalance()',
  'error HealthFactorLowerThanLiquidationThreshold()',
  'error LtvValidationFailed()',
])

export const poolErrorMessages: Record<string, string> = {
  InvalidAmount: 'The amount must be greater than zero.',
  ReserveInactive: 'This Aave market is not active.',
  ReserveFrozen: 'This Aave market is frozen; new deposits are disabled.',
  ReservePaused: 'This Aave market is paused.',
  SupplyCapExceeded: "The deposit would exceed Aave's supply cap for this market.",
  NotEnoughAvailableUserBalance: 'The amount exceeds your deposited balance.',
  HealthFactorLowerThanLiquidationThreshold:
    'This withdrawal would put an Aave loan backed by these funds at risk of liquidation.',
  LtvValidationFailed:
    'Aave blocks this withdrawal while you have an open loan on this account.',
}

// approve() is declared without a return value on purpose: USDT does not
// return a bool, and declaring one would make simulation fail to decode.
export const erc20Abi = parseAbi([
  'function balanceOf(address owner) view returns (uint256)',
  'function totalSupply() view returns (uint256)',
  'function allowance(address owner, address spender) view returns (uint256)',
  'function approve(address spender, uint256 amount)',
])

const RAY = 10n ** 27n
const SECONDS_PER_YEAR = 31_536_000

/** Supply APY from Aave's per-second-compounded liquidity rate (an APR in ray). */
export function liquidityRateToApy(currentLiquidityRate: bigint): number {
  const apr = Number(currentLiquidityRate) / Number(RAY)
  return (1 + apr / SECONDS_PER_YEAR) ** SECONDS_PER_YEAR - 1
}

export type ReserveStatus = {
  active: boolean
  frozen: boolean
  paused: boolean
  /** Supply cap in token base units, or null when uncapped. */
  supplyCap: bigint | null
}

// Bit layout from Aave v3 ReserveConfiguration.sol.
export function decodeReserveConfiguration(
  configuration: bigint,
  decimals: number,
): ReserveStatus {
  const bit = (i: bigint) => ((configuration >> i) & 1n) === 1n
  const capWholeTokens = (configuration >> 116n) & ((1n << 36n) - 1n)
  return {
    active: bit(56n),
    frozen: bit(57n),
    paused: bit(60n),
    supplyCap:
      capWholeTokens === 0n ? null : capWholeTokens * 10n ** BigInt(decimals),
  }
}

/** Total supplied as Aave counts it against the supply cap. */
export function totalSuppliedForCap(
  aTokenTotalSupply: bigint,
  accruedToTreasury: bigint,
  normalizedIncome: bigint,
): bigint {
  return aTokenTotalSupply + (accruedToTreasury * normalizedIncome) / RAY
}
