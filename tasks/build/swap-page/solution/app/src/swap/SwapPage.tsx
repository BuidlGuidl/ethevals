import { useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import {
  type Address,
  type Hash,
  BaseError,
  UserRejectedRequestError,
  formatUnits,
  parseUnits,
} from 'viem'
import {
  useBalance,
  useConfig,
  useConnect,
  useConnection,
  useConnectors,
  usePublicClient,
  useReadContracts,
  useSwitchChain,
} from 'wagmi'

import { chain, treasury } from '../chain.ts'
import { type SwapOutcome, executeSwap } from './execute.ts'
import {
  type Quote,
  type Token,
  FEE_BIPS,
  TOKENS,
  erc20Abi,
  getQuote,
  minimumOut,
} from './uniswap.ts'

const SLIPPAGE_OPTIONS = [10n, 50n, 100n, 300n] // bips
const QUOTE_REFRESH_MS = 15_000
const QUOTE_TTL_MS = 30_000
// Gas units reserved when the user hits "Max" on ETH (a swap uses ~150-200k).
const GAS_RESERVE_UNITS = 400_000n

const WARN_IMPACT_PPM = 10_000n // 1%
const HIGH_IMPACT_PPM = 50_000n // 5%
const MAX_IMPACT_PPM = 150_000n // 15%: refuse to swap

export function SwapPage() {
  const config = useConfig()
  const connection = useConnection()
  const publicClient = usePublicClient({ chainId: chain.id })
  const account = connection.address

  const [tokenIn, setTokenIn] = useState<Token>(TOKENS[0])
  const [tokenOut, setTokenOut] = useState<Token>(TOKENS[1])
  const [amountText, setAmountText] = useState('')
  const [slippageBips, setSlippageBips] = useState(50n)

  const [review, setReview] = useState<Quote | null>(null)
  const [progress, setProgress] = useState<string | null>(null)
  const [pendingHash, setPendingHash] = useState<Hash | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [priceNotice, setPriceNotice] = useState<string | null>(null)
  const [done, setDone] = useState<SwapOutcome | null>(null)

  const balances = useBalances(account)
  const now = useNow(review ? 1000 : null)
  const balanceIn = balances.of(tokenIn)

  const debouncedText = useDebounced(amountText, 350)
  const parsed = parseAmount(debouncedText, tokenIn)
  const amountIn = parsed.ok ? parsed.value : 0n

  const busy = progress !== null
  const quoteQuery = useQuery({
    queryKey: ['uniswapQuote', tokenIn.symbol, tokenOut.symbol, amountIn.toString()],
    queryFn: () => getQuote(publicClient!, tokenIn, tokenOut, amountIn),
    enabled: !!publicClient && amountIn > 0n && !review && !done,
    refetchInterval: QUOTE_REFRESH_MS,
    retry: 1,
  })
  // Don't show a quote for an amount the user has since edited.
  const quote =
    quoteQuery.data &&
    quoteQuery.data.amountIn === amountIn &&
    quoteQuery.data.tokenIn === tokenIn &&
    quoteQuery.data.tokenOut === tokenOut
      ? quoteQuery.data
      : undefined

  // Reset the flow if the user switches account.
  useEffect(() => {
    setReview(null)
    setDone(null)
    setError(null)
  }, [account])

  const wrongChain = connection.status === 'connected' && connection.chainId !== chain.id
  const insufficient = balanceIn !== undefined && amountIn > balanceIn

  function selectToken(side: 'in' | 'out', token: Token) {
    const other = side === 'in' ? tokenOut : tokenIn
    if (token === other) return flip()
    if (side === 'in') setTokenIn(token)
    else setTokenOut(token)
  }

  function flip() {
    setTokenIn(tokenOut)
    setTokenOut(tokenIn)
    setAmountText('')
  }

  async function setMax() {
    if (balanceIn === undefined || !publicClient) return
    let max = balanceIn
    if (!tokenIn.address) {
      const fees = await publicClient.estimateFeesPerGas()
      const reserve = fees.maxFeePerGas * GAS_RESERVE_UNITS
      max = balanceIn > reserve ? balanceIn - reserve : 0n
    }
    setAmountText(formatUnits(max, tokenIn.decimals))
  }

  async function confirm(q: Quote) {
    if (!account) return
    setError(null)
    setPendingHash(null)
    try {
      const fresh = await getQuote(publicClient!, q.tokenIn, q.tokenOut, q.amountIn)
      if ((fresh.netOut > q.netOut ? fresh.netOut - q.netOut : q.netOut - fresh.netOut) * 100n > q.netOut) {
        setReview(fresh)
        setPriceNotice('The price changed. Review the fresh quote and confirm again.')
        return
      }
      setDone(
        await executeSwap({
          config,
          chainId: chain.id,
          quote: q,
          slippageBips,
          account,
          treasury,
          onProgress: setProgress,
          onSubmitted: setPendingHash,
        }),
      )
      setReview(null)
      setAmountText('')
    } catch (e) {
      setError(describeError(e))
    } finally {
      setProgress(null)
      balances.refetch()
    }
  }

  if (connection.status !== 'connected') return <ConnectPrompt />

  if (done) return <SwapReceipt done={done} onNewSwap={() => setDone(null)} />

  if (review) {
    const expired = now - review.quotedAt > QUOTE_TTL_MS
    return (
      <section className="swap-card">
        <h2>Review swap</h2>
        <QuoteDetails quote={review} slippageBips={slippageBips} />
        {priceNotice && <p className="warn">{priceNotice}</p>}
        <ImpactWarning quote={review} />
        {expired && !busy && (
          <p className="warn">This quote is more than 30 seconds old. Get a fresh one before swapping.</p>
        )}
        {progress && <p className="progress">{progress}</p>}
        {pendingHash && <TxLink hash={pendingHash} />}
        {error && <p className="error">{error}</p>}
        <div className="actions">
          <button type="button" disabled={busy} onClick={() => setReview(null)}>
            Back
          </button>
          {expired ? (
            <button
              type="button"
              className="primary"
              disabled={busy}
              onClick={async () => {
                setError(null)
                try {
                  setReview(await getQuote(publicClient!, review.tokenIn, review.tokenOut, review.amountIn))
                } catch (e) {
                  setError(describeError(e))
                }
              }}
            >
              Refresh quote
            </button>
          ) : (
            <button
              type="button"
              className="primary"
              disabled={busy || wrongChain || review.priceImpactPpm >= MAX_IMPACT_PPM}
              onClick={() => confirm(review)}
            >
              {review.priceImpactPpm >= HIGH_IMPACT_PPM ? 'Swap anyway' : 'Confirm swap'}
            </button>
          )}
        </div>
      </section>
    )
  }

  let disabledReason: string | null = null
  if (wrongChain) disabledReason = `Switch to ${chain.name}`
  else if (!parsed.ok) disabledReason = parsed.error
  else if (amountIn === 0n) disabledReason = 'Enter an amount'
  else if (insufficient) disabledReason = `Insufficient ${tokenIn.symbol} balance`
  else if (!quote) disabledReason = quoteQuery.isError ? 'No quote available' : 'Fetching quote…'
  else if (quote.priceImpactPpm >= MAX_IMPACT_PPM) disabledReason = 'Price impact too high'

  return (
    <section className="swap-card">
      <h2>Swap</h2>
      {wrongChain && <WrongChain />}

      <div className="field">
        <div className="field-header">
          <span>You pay</span>
          <span>
            Balance: {balanceIn === undefined ? '…' : fmt(balanceIn, tokenIn)}{' '}
            <button type="button" className="link" onClick={setMax} disabled={!balanceIn}>
              Max
            </button>
          </span>
        </div>
        <div className="field-row">
          <input
            inputMode="decimal"
            placeholder="0.0"
            value={amountText}
            onChange={(e) => {
              const v = e.target.value.replace(',', '.')
              if (/^\d*\.?\d*$/.test(v)) setAmountText(v)
            }}
          />
          <TokenSelect value={tokenIn} onChange={(t) => selectToken('in', t)} />
        </div>
      </div>

      <button type="button" className="flip" onClick={flip} aria-label="Swap direction">
        ↓↑
      </button>

      <div className="field">
        <div className="field-header">
          <span>You receive (estimated)</span>
          <span>Balance: {balances.of(tokenOut) === undefined ? '…' : fmt(balances.of(tokenOut)!, tokenOut)}</span>
        </div>
        <div className="field-row">
          <output>{quote ? fmt(quote.netOut, tokenOut) : amountIn > 0n && quoteQuery.isFetching ? '…' : '0.0'}</output>
          <TokenSelect value={tokenOut} onChange={(t) => selectToken('out', t)} />
        </div>
      </div>

      <div className="slippage">
        <span>Max slippage</span>
        {SLIPPAGE_OPTIONS.map((bips) => (
          <button
            key={bips.toString()}
            type="button"
            className={bips === slippageBips ? 'selected' : ''}
            onClick={() => setSlippageBips(bips)}
          >
            {formatBips(bips)}
          </button>
        ))}
      </div>

      {quote && <QuoteDetails quote={quote} slippageBips={slippageBips} />}
      {quote && <ImpactWarning quote={quote} />}
      {quoteQuery.isError && amountIn > 0n && !quote && (
        <p className="error">Couldn't get a Uniswap quote: {describeError(quoteQuery.error)}</p>
      )}

      <button
        type="button"
        className="primary wide"
        disabled={disabledReason !== null}
        onClick={() => {
          setError(null)
          setReview(quote!)
        }}
      >
        {disabledReason ?? 'Review swap'}
      </button>
    </section>
  )
}

function QuoteDetails({ quote, slippageBips }: { quote: Quote; slippageBips: bigint }) {
  const { tokenIn, tokenOut } = quote
  const { minNet } = minimumOut(quote, slippageBips)
  return (
    <dl className="details">
      <dt>You pay</dt>
      <dd>
        {fmt(quote.amountIn, tokenIn)} {tokenIn.symbol}
      </dd>
      <dt>You receive (estimated)</dt>
      <dd className="strong">
        {fmt(quote.netOut, tokenOut)} {tokenOut.symbol}
      </dd>
      <dt>Minimum received ({formatBips(slippageBips)} slippage)</dt>
      <dd>
        {fmt(minNet, tokenOut)} {tokenOut.symbol}
      </dd>
      <dt>Rate (after all fees)</dt>
      <dd>
        1 {tokenIn.symbol} = {formatRate(quote.netOut, tokenOut, quote.amountIn, tokenIn)} {tokenOut.symbol}
      </dd>
      <dt>Service fee ({formatBips(FEE_BIPS)})</dt>
      <dd>
        {fmt(quote.feeAmount, tokenOut)} {tokenOut.symbol}
      </dd>
      <dt>Price impact</dt>
      <dd className={impactClass(quote.priceImpactPpm)}>{formatPpm(quote.priceImpactPpm)}</dd>
      <dt>Route</dt>
      <dd>
        Uniswap v3 · {tokenIn.symbol}/{tokenOut.symbol} {formatPpm(BigInt(quote.poolFee))} pool
      </dd>
    </dl>
  )
}

function ImpactWarning({ quote }: { quote: Quote }) {
  if (quote.priceImpactPpm >= MAX_IMPACT_PPM)
    return (
      <p className="error">
        Price impact is {formatPpm(quote.priceImpactPpm)}. Uniswap doesn't have enough liquidity for
        this size. Try a smaller amount.
      </p>
    )
  if (quote.priceImpactPpm >= HIGH_IMPACT_PPM)
    return (
      <p className="error">
        High price impact ({formatPpm(quote.priceImpactPpm)}). You'll get noticeably less than the
        market price.
      </p>
    )
  if (quote.priceImpactPpm >= WARN_IMPACT_PPM)
    return <p className="warn">Price impact is {formatPpm(quote.priceImpactPpm)}.</p>
  return null
}

function SwapReceipt({ done, onNewSwap }: { done: SwapOutcome; onNewSwap: () => void }) {
  const { quote, result } = done
  const { tokenIn, tokenOut } = quote
  const diff = result.amountOut - quote.netOut
  return (
    <section className="swap-card">
      <h2>Swap complete</h2>
      <dl className="details">
        <dt>You received</dt>
        <dd className="strong">
          {fmt(result.amountOut, tokenOut)} {tokenOut.symbol}
        </dd>
        <dt>Quoted</dt>
        <dd>
          {fmt(quote.netOut, tokenOut)} {tokenOut.symbol}{' '}
          {diff !== 0n && (
            <span className={diff > 0n ? 'good' : 'warn'}>
              ({diff > 0n ? '+' : '−'}
              {fmt(diff > 0n ? diff : -diff, tokenOut)})
            </span>
          )}
        </dd>
        <dt>You paid</dt>
        <dd>
          {fmt(result.amountIn, tokenIn)} {tokenIn.symbol}
        </dd>
        <dt>Rate (after all fees)</dt>
        <dd>
          1 {tokenIn.symbol} = {formatRate(result.amountOut, tokenOut, result.amountIn, tokenIn)}{' '}
          {tokenOut.symbol}
        </dd>
        <dt>Service fee ({formatBips(FEE_BIPS)})</dt>
        <dd>
          {fmt(result.feePaid, tokenOut)} {tokenOut.symbol}
        </dd>
        <dt>Network fee</dt>
        <dd>{fmt(done.gasCost, TOKENS[0])} ETH</dd>
      </dl>
      <TxLink hash={done.hash} />
      <button type="button" className="primary wide" onClick={onNewSwap}>
        New swap
      </button>
    </section>
  )
}

function TokenSelect({ value, onChange }: { value: Token; onChange: (t: Token) => void }) {
  const [open, setOpen] = useState(false)
  return (
    <div>
      <button type="button" onClick={() => setOpen(true)}>{value.symbol}</button>
      {open && (
        <div role="dialog" aria-label="Choose token">
          {TOKENS.map((token) => (
            <button key={token.symbol} type="button" onClick={() => { onChange(token); setOpen(false) }}>
              {token.symbol}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function TxLink({ hash }: { hash: Hash }) {
  return (
    <p className="tx">
      Transaction:{' '}
      <a href={`${chain.blockExplorers.default.url}/tx/${hash}`} target="_blank" rel="noreferrer">
        {hash.slice(0, 10)}…{hash.slice(-8)}
      </a>
    </p>
  )
}

function WrongChain() {
  const { switchChain, isPending, error } = useSwitchChain()
  return (
    <div className="warn">
      Your wallet is on the wrong network.{' '}
      <button type="button" disabled={isPending} onClick={() => switchChain({ chainId: chain.id })}>
        Switch to {chain.name}
      </button>
      {error && <div className="error">{describeError(error)}</div>}
    </div>
  )
}

function ConnectPrompt() {
  const connectors = useConnectors()
  const { connect, error, isPending } = useConnect()
  return (
    <section className="swap-card">
      <h2>Swap</h2>
      <p>Connect a wallet to swap ETH, USDC and USDT on Uniswap.</p>
      <div className="actions">
        {connectors.map((connector) => (
          <button
            key={connector.uid}
            type="button"
            disabled={isPending}
            onClick={() => connect({ connector, chainId: chain.id })}
          >
            {connector.name}
          </button>
        ))}
      </div>
      {connectors.length === 0 && <p className="warn">No browser wallet detected.</p>}
      {error && <p className="error">{describeError(error)}</p>}
    </section>
  )
}

function useBalances(account: Address | undefined) {
  const eth = useBalance({ address: account, chainId: chain.id })
  const erc20s = TOKENS.filter((t) => t.address)
  const tokens = useReadContracts({
    allowFailure: false,
    contracts: erc20s.map((t) => ({
      address: t.address!,
      abi: erc20Abi,
      functionName: 'balanceOf',
      args: [account!],
      chainId: chain.id,
    })),
    query: { enabled: !!account },
  })
  return {
    of(token: Token): bigint | undefined {
      if (!token.address) return eth.data?.value
      return tokens.data?.[erc20s.indexOf(token)]
    },
    refetch() {
      eth.refetch()
      tokens.refetch()
    },
  }
}

function useNow(intervalMs: number | null) {
  const [now, setNow] = useState(Date.now)
  useEffect(() => {
    if (intervalMs === null) return
    setNow(Date.now())
    const id = setInterval(() => setNow(Date.now()), intervalMs)
    return () => clearInterval(id)
  }, [intervalMs])
  return now
}

function useDebounced<T>(value: T, ms: number) {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), ms)
    return () => clearTimeout(id)
  }, [value, ms])
  return debounced
}

function parseAmount(
  text: string,
  token: Token,
): { ok: true; value: bigint } | { ok: false; error: string } {
  if (text === '' || text === '.') return { ok: true, value: 0n }
  const fraction = text.split('.')[1] ?? ''
  if (fraction.length > token.decimals)
    return { ok: false, error: `${token.symbol} has at most ${token.decimals} decimals` }
  return { ok: true, value: parseUnits(text, token.decimals) }
}

// Truncates (never rounds up) so displayed amounts are never more than reality.
function fmt(value: bigint, token: Token) {
  const [whole, fraction = ''] = formatUnits(value, token.decimals).split('.')
  const shown = fraction.slice(0, token.displayDecimals).replace(/0+$/, '')
  if (value > 0n && whole === '0' && shown === '')
    return `<0.${'0'.repeat(token.displayDecimals - 1)}1`
  return `${BigInt(whole).toLocaleString('en-US')}${shown ? `.${shown}` : ''}`
}

function formatRate(out: bigint, tokenOut: Token, amountIn: bigint, tokenIn: Token) {
  if (amountIn === 0n) return '—'
  const rate = Number(formatUnits(out, tokenOut.decimals)) / Number(formatUnits(amountIn, tokenIn.decimals))
  return rate.toLocaleString('en-US', { maximumSignificantDigits: 6 })
}

function formatBips(bips: bigint) {
  return `${Number(bips) / 100}%`
}

function formatPpm(ppm: bigint) {
  if (ppm > 0n && ppm < 100n) return '<0.01%'
  return `${(Number(ppm) / 10_000).toLocaleString('en-US', { maximumFractionDigits: 2 })}%`
}

function impactClass(ppm: bigint) {
  if (ppm >= HIGH_IMPACT_PPM) return 'error'
  if (ppm >= WARN_IMPACT_PPM) return 'warn'
  return ''
}

function describeError(e: unknown): string {
  if (e instanceof BaseError) {
    if (e.walk((err) => err instanceof UserRejectedRequestError))
      return 'You rejected the request in your wallet.'
    const text = `${e.message}`
    if (text.includes('Too little received') || text.includes('Insufficient token'))
      return 'The price moved beyond your slippage tolerance. Go back and get a new quote, or raise the max slippage.'
    if (text.includes('Transaction too old'))
      return 'The swap deadline passed before it was mined. Please try again.'
    return e.shortMessage
  }
  return e instanceof Error ? e.message : String(e)
}
