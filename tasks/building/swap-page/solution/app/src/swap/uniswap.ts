import {
  type Address,
  type Hex,
  type PublicClient,
  type TransactionReceipt,
  BaseError,
  ContractFunctionRevertedError,
  encodeFunctionData,
  isAddressEqual,
  parseAbi,
  parseEventLogs,
} from 'viem'

// Uniswap v3 deployments on Ethereum mainnet.
export const SWAP_ROUTER_02: Address = '0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45'
export const QUOTER_V2: Address = '0x61fFE014bA17989E743c5F6cB21bF9697530B21e'
export const V3_FACTORY: Address = '0x1F98431c8aD98523631AE4a59f267346ea31F984'
export const WETH: Address = '0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2'

// SwapRouter02 sentinel recipient meaning "keep the output in the router" so a
// later call in the same multicall can split it between the user and treasury.
const ROUTER_AS_RECIPIENT: Address = '0x0000000000000000000000000000000000000002'

// Our cut of every swap: 25 bips = 0.25%, taken from the output token.
export const FEE_BIPS = 25n
const BIPS = 10_000n

export const FEE_TIERS = [100, 500, 3000, 10000] as const

export type Token = {
  symbol: 'ETH' | 'USDC' | 'USDT'
  decimals: number
  displayDecimals: number
  // `null` for native ETH; the swap routes through WETH.
  address: Address | null
}

export const TOKENS: readonly Token[] = [
  { symbol: 'ETH', decimals: 18, displayDecimals: 6, address: null },
  {
    symbol: 'USDC',
    decimals: 6,
    displayDecimals: 4,
    address: '0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48',
  },
  {
    symbol: 'USDT',
    decimals: 6,
    displayDecimals: 4,
    address: '0xdAC17F958D2ee523a2206206994597C13D831ec7',
  },
]

export const routingAddress = (token: Token): Address => token.address ?? WETH

// QuoterV2 functions aren't marked view (they revert internally to return the
// result) but are meant to be eth_call'd, so they're declared view here.
const quoterAbi = parseAbi([
  'struct QuoteExactInputSingleParams { address tokenIn; address tokenOut; uint256 amountIn; uint24 fee; uint160 sqrtPriceLimitX96; }',
  'function quoteExactInputSingle(QuoteExactInputSingleParams params) view returns (uint256 amountOut, uint160 sqrtPriceX96After, uint32 initializedTicksCrossed, uint256 gasEstimate)',
])

const factoryAbi = parseAbi([
  'function getPool(address tokenA, address tokenB, uint24 fee) view returns (address)',
])

const poolAbi = parseAbi([
  'function slot0() view returns (uint160 sqrtPriceX96, int24 tick, uint16 observationIndex, uint16 observationCardinality, uint16 observationCardinalityNext, uint8 feeProtocol, bool unlocked)',
])

export const routerAbi = parseAbi([
  'struct ExactInputSingleParams { address tokenIn; address tokenOut; uint24 fee; address recipient; uint256 amountIn; uint256 amountOutMinimum; uint160 sqrtPriceLimitX96; }',
  'function exactInputSingle(ExactInputSingleParams params) payable returns (uint256 amountOut)',
  'function multicall(uint256 deadline, bytes[] data) payable returns (bytes[] results)',
  'function sweepTokenWithFee(address token, uint256 amountMinimum, address recipient, uint256 feeBips, address feeRecipient) payable',
  'function unwrapWETH9WithFee(uint256 amountMinimum, address recipient, uint256 feeBips, address feeRecipient) payable',
  'function refundETH() payable',
])

// `approve` is declared without a return value because USDT doesn't return one.
export const erc20Abi = parseAbi([
  'function balanceOf(address owner) view returns (uint256)',
  'function allowance(address owner, address spender) view returns (uint256)',
  'function approve(address spender, uint256 amount)',
  'event Transfer(address indexed from, address indexed to, uint256 value)',
])

const wethAbi = parseAbi([
  'event Deposit(address indexed dst, uint256 wad)',
  'event Withdrawal(address indexed src, uint256 wad)',
])

const isRevert = (e: unknown) =>
  e instanceof BaseError &&
  !!e.walk((cause) => cause instanceof ContractFunctionRevertedError)

export const feeOf = (gross: bigint) => (gross * FEE_BIPS) / BIPS

export type Quote = {
  tokenIn: Token
  tokenOut: Token
  amountIn: bigint
  poolFee: number
  pool: Address
  // What the pool pays out, before our fee.
  grossOut: bigint
  // Our 0.25% cut of grossOut.
  feeAmount: bigint
  // What the user receives.
  netOut: bigint
  // Price impact of this trade vs. the pool's current price, in parts per million.
  // Also catches trades bigger than the pool can fill, which the quoter
  // reports as a partial fill.
  priceImpactPpm: bigint
  quotedAt: number
}

export async function getQuote(
  client: PublicClient,
  tokenIn: Token,
  tokenOut: Token,
  amountIn: bigint,
): Promise<Quote> {
  const inAddr = routingAddress(tokenIn)
  const outAddr = routingAddress(tokenOut)

  // One eth_call per fee tier rather than a Multicall3 batch, so a tier that
  // burns lots of gas walking ticks can't starve the others.
  const quotes = await Promise.allSettled(
    FEE_TIERS.map((fee) =>
      client.readContract({
        address: QUOTER_V2,
        abi: quoterAbi,
        functionName: 'quoteExactInputSingle',
        args: [
          { tokenIn: inAddr, tokenOut: outAddr, amountIn, fee, sqrtPriceLimitX96: 0n },
        ],
      }),
    ),
  )

  let best: { fee: number; amountOut: bigint } | undefined
  quotes.forEach((q, i) => {
    if (q.status !== 'fulfilled') return
    const amountOut = q.value[0]
    if (!best || amountOut > best.amountOut)
      best = { fee: FEE_TIERS[i], amountOut }
  })
  if (!best || best.amountOut === 0n) {
    // A revert means the pool doesn't exist or can't fill the trade; anything
    // else (timeout, RPC down) is surfaced as-is rather than as "no liquidity".
    const failure = quotes.find(
      (q) => q.status === 'rejected' && !isRevert(q.reason),
    )
    if (failure?.status === 'rejected') throw failure.reason
    throw new Error('No Uniswap v3 pool can fill this trade')
  }

  const pool = await client.readContract({
    address: V3_FACTORY,
    abi: factoryAbi,
    functionName: 'getPool',
    args: [inAddr, outAddr, best.fee],
  })
  const [sqrtPriceX96] = await client.readContract({
    address: pool,
    abi: poolAbi,
    functionName: 'slot0',
  })

  // Output at the pool's current price, after the LP fee but with no price movement.
  const zeroForOne = BigInt(inAddr) < BigInt(outAddr)
  const priceX192 = sqrtPriceX96 * sqrtPriceX96
  const spotOut = zeroForOne
    ? (amountIn * priceX192) >> 192n
    : (amountIn << 192n) / priceX192
  const idealOut = (spotOut * BigInt(1_000_000 - best.fee)) / 1_000_000n
  const priceImpactPpm =
    idealOut > best.amountOut
      ? ((idealOut - best.amountOut) * 1_000_000n) / idealOut
      : 0n

  const feeAmount = feeOf(best.amountOut)
  return {
    tokenIn,
    tokenOut,
    amountIn,
    poolFee: best.fee,
    pool,
    grossOut: best.amountOut,
    feeAmount,
    netOut: best.amountOut - feeAmount,
    priceImpactPpm,
    quotedAt: Date.now(),
  }
}

export function minimumOut(quote: Quote, slippageBips: bigint) {
  const minGross = (quote.grossOut * (BIPS - slippageBips)) / BIPS
  return { minGross, minNet: minGross - feeOf(minGross) }
}

/**
 * One SwapRouter02 multicall that swaps into the router, then pays the output
 * out with FEE_BIPS going to the treasury and the rest to the user.
 */
export function buildSwapTx({
  quote,
  slippageBips,
  account,
  treasury,
  deadline,
}: {
  quote: Quote
  slippageBips: bigint
  account: Address
  treasury: Address
  deadline: bigint
}): { to: Address; data: Hex; value: bigint } {
  const { minGross } = minimumOut(quote, slippageBips)

  const swap = encodeFunctionData({
    abi: routerAbi,
    functionName: 'exactInputSingle',
    args: [
      {
        tokenIn: routingAddress(quote.tokenIn),
        tokenOut: routingAddress(quote.tokenOut),
        fee: quote.poolFee,
        recipient: ROUTER_AS_RECIPIENT,
        amountIn: quote.amountIn,
        amountOutMinimum: minGross,
        sqrtPriceLimitX96: 0n,
      },
    ],
  })

  const payout = quote.tokenOut.address
    ? encodeFunctionData({
        abi: routerAbi,
        functionName: 'sweepTokenWithFee',
        args: [quote.tokenOut.address, minGross, account, FEE_BIPS, treasury],
      })
    : encodeFunctionData({
        abi: routerAbi,
        functionName: 'unwrapWETH9WithFee',
        args: [minGross, account, FEE_BIPS, treasury],
      })

  return {
    to: SWAP_ROUTER_02,
    data: encodeFunctionData({
      abi: routerAbi,
      functionName: 'multicall',
      // If the pool can't absorb the whole input, refundETH returns unspent ETH
      // instead of leaving it in the router.
      args: [
        deadline,
        quote.tokenIn.address
          ? [swap, payout]
          : [swap, payout, encodeFunctionData({ abi: routerAbi, functionName: 'refundETH' })],
      ],
    }),
    // For ETH input the router wraps msg.value into WETH itself.
    value: quote.tokenIn.address ? 0n : quote.amountIn,
  }
}

export type SwapResult = {
  amountIn: bigint
  amountOut: bigint
  feePaid: bigint
}

/** Reads what was actually spent and received from the swap receipt's logs. */
export function parseSwapReceipt(
  receipt: TransactionReceipt,
  tokenIn: Token,
  tokenOut: Token,
  account: Address,
  treasury: Address,
): SwapResult {
  const transfers = parseEventLogs({
    abi: erc20Abi,
    eventName: 'Transfer',
    logs: receipt.logs,
  })
  const wethEvents = parseEventLogs({
    abi: wethAbi,
    logs: receipt.logs.filter((l) => isAddressEqual(l.address, WETH)),
  })

  const sumTransfers = (token: Address, from: Address, to?: Address) =>
    transfers
      .filter(
        (t) =>
          isAddressEqual(t.address, token) &&
          isAddressEqual(t.args.from, from) &&
          (!to || isAddressEqual(t.args.to, to)),
      )
      .reduce((sum, t) => sum + t.args.value, 0n)

  const amountIn = tokenIn.address
    ? sumTransfers(tokenIn.address, account)
    : wethEvents
        .filter(
          (e) =>
            e.eventName === 'Deposit' &&
            isAddressEqual(e.args.dst, SWAP_ROUTER_02),
        )
        .reduce((sum, e) => sum + e.args.wad, 0n)

  if (tokenOut.address) {
    return {
      amountIn,
      amountOut: sumTransfers(tokenOut.address, SWAP_ROUTER_02, account),
      feePaid: sumTransfers(tokenOut.address, SWAP_ROUTER_02, treasury),
    }
  }

  // ETH payouts emit no logs. unwrapWETH9WithFee unwraps the router's whole WETH
  // balance and splits it exactly as feeOf() does, so derive both legs from that.
  const unwrapped = wethEvents
    .filter(
      (e) =>
        e.eventName === 'Withdrawal' &&
        isAddressEqual(e.args.src, SWAP_ROUTER_02),
    )
    .reduce((sum, e) => sum + e.args.wad, 0n)
  const feePaid = feeOf(unwrapped)
  return { amountIn, amountOut: unwrapped - feePaid, feePaid }
}
