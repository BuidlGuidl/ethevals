import { useState } from 'react'
import { type Address, formatUnits } from 'viem'
import { useConfig, useConnection } from 'wagmi'

import { SAVINGS_TOKENS, type SavingsToken } from './aave.ts'
import { formatAmount, formatApy, parseAmount } from './format.ts'
import { describeError, deposit, withdraw } from './transactions.ts'
import { type SavingsMarket, useSavingsMarket } from './useSavingsMarket.ts'

export function SavingsPage() {
  const connection = useConnection()
  const account = connection.status === 'connected' ? connection.address : undefined

  return (
    <div className="savings">
      <h2>Savings</h2>
      <p className="muted">
        Earn interest on your stablecoins by depositing them into Aave v3 on
        Ethereum. Interest accrues every block and you can withdraw at any time.
      </p>
      {!account && <p className="notice">Connect a wallet to deposit or withdraw.</p>}
      <div className="savings-grid">
        {SAVINGS_TOKENS.map((token) => (
          <SavingsCard key={token.symbol} token={token} account={account} />
        ))}
      </div>
    </div>
  )
}

function SavingsCard({ token, account }: { token: SavingsToken; account?: Address }) {
  const market = useSavingsMarket(token, account)
  const data = market.data

  return (
    <section className="savings-card">
      <header>
        <h3>{token.symbol}</h3>
        <div className="apy">
          {data ? formatApy(data.apy) : '—'}
          <span className="muted"> APY</span>
        </div>
      </header>

      {market.isError && !data && (
        <p className="error">Could not load Aave data: {describeError(market.error)}</p>
      )}

      {data && <ReserveWarnings token={token} market={data} />}

      {account && (
        <dl>
          <dt>Deposited (incl. interest)</dt>
          <dd>{data?.user ? `${formatAmount(data.user.deposited, token.decimals, token.decimals)} ${token.symbol}` : '—'}</dd>
          <dt>Wallet balance</dt>
          <dd>{data?.user ? `${formatAmount(data.user.walletBalance, token.decimals)} ${token.symbol}` : '—'}</dd>
        </dl>
      )}

      {account && data?.user && (
        <SavingsForm
          token={token}
          account={account}
          market={data}
          user={data.user}
          onDone={() => market.refetch()}
        />
      )}
    </section>
  )
}

function ReserveWarnings({ token, market }: { token: SavingsToken; market: SavingsMarket }) {
  const { status } = market
  if (!status.active || status.paused)
    return <p className="notice">Aave has paused the {token.symbol} market. Deposits and withdrawals are unavailable.</p>
  if (status.frozen)
    return <p className="notice">Aave has frozen the {token.symbol} market. New deposits are disabled; withdrawals still work.</p>
  if (market.remainingSupplyCap === 0n)
    return <p className="notice">The {token.symbol} market has reached its supply cap. New deposits are not possible right now.</p>
  return null
}

type Mode = 'deposit' | 'withdraw'

function SavingsForm({
  token,
  account,
  market,
  user,
  onDone,
}: {
  token: SavingsToken
  account: Address
  market: SavingsMarket
  user: NonNullable<SavingsMarket['user']>
  onDone: () => void
}) {
  const config = useConfig()
  const [mode, setMode] = useState<Mode>('deposit')
  const [input, setInput] = useState('')
  // "Max" withdrawals are sent as uint256 max so interest accrued after the
  // click is included and no dust is left behind.
  const [withdrawAll, setWithdrawAll] = useState(false)
  const [progress, setProgress] = useState<string>()
  const [result, setResult] = useState<{ ok: boolean; message: string }>()

  const busy = progress !== undefined
  const { status } = market
  const amount = parseAmount(input, token.decimals)
  const fmt = (v: bigint) => `${formatAmount(v, token.decimals, token.decimals)} ${token.symbol}`

  const validation = (() => {
    if (withdrawAll && mode === 'withdraw') {
      if (user.deposited === 0n) return 'Nothing to withdraw.'
      if (user.deposited > market.availableLiquidity)
        return `Aave currently has only ${fmt(market.availableLiquidity)} available to withdraw.`
      return null
    }
    if (input.trim() === '') return ''
    if (amount === undefined) return `Enter a valid amount (up to ${token.decimals} decimals).`
    if (amount === 0n) return 'Amount must be greater than zero.'
    if (mode === 'deposit') {
      if (!status.active || status.paused || status.frozen) return 'Deposits are currently disabled for this market.'
      if (amount > user.walletBalance) return `Insufficient ${token.symbol} balance.`
      if (market.remainingSupplyCap !== null && amount > market.remainingSupplyCap)
        return `Exceeds Aave's supply cap; at most ${fmt(market.remainingSupplyCap)} can be deposited.`
    } else {
      if (!status.active || status.paused) return 'Withdrawals are currently disabled for this market.'
      if (amount > user.deposited) return 'Amount exceeds your deposited balance.'
      if (amount > market.availableLiquidity)
        return `Aave currently has only ${fmt(market.availableLiquidity)} available to withdraw.`
    }
    return null
  })()

  function switchMode(next: Mode) {
    setMode(next)
    setInput('')
    setWithdrawAll(false)
    setResult(undefined)
  }

  function setMax() {
    if (mode === 'deposit') {
      setInput(formatUnits(user.walletBalance, token.decimals))
    } else {
      setInput(formatUnits(user.deposited, token.decimals))
      setWithdrawAll(true)
    }
    setResult(undefined)
  }

  async function submit() {
    if (validation !== null || busy) return
    setResult(undefined)
    setProgress('Preparing…')
    try {
      if (mode === 'deposit') {
        await deposit(config, { token, amount: amount!, account, onProgress: setProgress })
        setResult({ ok: true, message: `Deposited ${input} ${token.symbol}.` })
      } else {
        await withdraw(config, { token, amount: withdrawAll ? 'max' : amount!, account, onProgress: setProgress })
        setResult({ ok: true, message: withdrawAll ? `Withdrew all ${token.symbol}.` : `Withdrew ${input} ${token.symbol}.` })
      }
      setInput('')
      setWithdrawAll(false)
    } catch (error) {
      setResult({ ok: false, message: describeError(error) })
    } finally {
      setProgress(undefined)
      onDone()
    }
  }

  return (
    <form
      className="savings-form"
      onSubmit={(e) => {
        e.preventDefault()
        void submit()
      }}
    >
      <div className="tabs" role="tablist">
        {(['deposit', 'withdraw'] as const).map((m) => (
          <button
            key={m}
            type="button"
            role="tab"
            aria-selected={mode === m}
            className={mode === m ? 'active' : ''}
            disabled={busy}
            onClick={() => switchMode(m)}
          >
            {m === 'deposit' ? 'Deposit' : 'Withdraw'}
          </button>
        ))}
      </div>

      <div className="amount-row">
        <input
          inputMode="decimal"
          placeholder="0.00"
          aria-label={`${mode === 'deposit' ? 'Deposit' : 'Withdraw'} amount in ${token.symbol}`}
          value={input}
          disabled={busy}
          onChange={(e) => {
            setInput(e.target.value)
            setWithdrawAll(false)
            setResult(undefined)
          }}
        />
        <span className="unit">{token.symbol}</span>
        <button type="button" onClick={setMax} disabled={busy}>
          Max
        </button>
      </div>
      {withdrawAll && mode === 'withdraw' && (
        <p className="muted small">Withdraws your full balance, including interest accrued until the transaction is mined.</p>
      )}

      <button type="submit" className="primary" disabled={busy || validation !== null}>
        {busy ? 'Working…' : mode === 'deposit' ? `Deposit ${token.symbol}` : `Withdraw ${token.symbol}`}
      </button>

      {validation && <p className="error">{validation}</p>}
      {progress && <p className="muted">{progress}</p>}
      {result && <p className={result.ok ? 'success' : 'error'}>{result.message}</p>}
    </form>
  )
}
