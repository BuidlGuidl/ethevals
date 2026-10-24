import { formatUnits, parseUnits } from 'viem'

/** Formats base units with thousands separators, keeping `maxDecimals` (truncated, never rounded up). */
export function formatAmount(value: bigint, decimals: number, maxDecimals = 2): string {
  const [whole, fraction = ''] = formatUnits(value, decimals).split('.')
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  const trimmed = fraction.slice(0, maxDecimals).padEnd(maxDecimals, '0')
  return maxDecimals > 0 ? `${grouped}.${trimmed}` : grouped
}

export function formatApy(apy: number): string {
  return `${(apy * 100).toFixed(2)}%`
}

/** Parses user input into base units; returns undefined for empty, malformed, or over-precise input. */
export function parseAmount(input: string, decimals: number): bigint | undefined {
  const value = input.trim()
  if (!new RegExp(`^(\\d+\\.?\\d{0,${decimals}}|\\.\\d{1,${decimals}})$`).test(value)) return undefined
  return parseUnits(value, decimals)
}
