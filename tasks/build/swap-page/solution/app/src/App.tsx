import { useEffect, useState } from 'react'
import { useConnect, useConnection, useConnectors, useDisconnect } from 'wagmi'

import { SwapPage } from './swap/SwapPage.tsx'

function usePage() {
  const [hash, setHash] = useState(window.location.hash)
  useEffect(() => {
    const onChange = () => setHash(window.location.hash)
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])
  return hash === '#/' ? 'wallet' : 'swap'
}

function App() {
  const page = usePage()

  return (
    <>
      <nav className="nav">
        <a href="#/" className={page === 'wallet' ? 'active' : ''}>
          Wallet
        </a>
        <a href="#/swap" className={page === 'swap' ? 'active' : ''}>
          Swap
        </a>
      </nav>
      {page === 'swap' ? <SwapPage /> : <WalletPage />}
    </>
  )
}

function WalletPage() {
  const connection = useConnection()
  const { connect, status, error } = useConnect()
  const connectors = useConnectors()
  const { disconnect } = useDisconnect()

  return (
    <>
      <div>
        <h2>Connection</h2>

        <div>
          status: {connection.status}
          <br />
          addresses: {JSON.stringify(connection.addresses)}
          <br />
          chainId: {connection.chainId}
        </div>

        {connection.status === 'connected' && (
          <button type="button" onClick={() => disconnect()}>
            Disconnect
          </button>
        )}
      </div>

      <div>
        <h2>Connect</h2>
        {connectors.map((connector) => (
          <button
            key={connector.uid}
            onClick={() => connect({ connector })}
            type="button"
          >
            {connector.name}
          </button>
        ))}
        <div>{status}</div>
        <div>{error?.message}</div>
      </div>
    </>
  )
}

export default App
