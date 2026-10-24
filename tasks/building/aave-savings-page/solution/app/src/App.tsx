import { useEffect, useState } from 'react'
import { useConnect, useConnection, useConnectors, useDisconnect } from 'wagmi'

import { SavingsPage } from './savings/SavingsPage.tsx'

const pages = { wallet: 'Wallet', savings: 'Savings' } as const
type Page = keyof typeof pages

function pageFromHash(): Page {
  const hash = window.location.hash.slice(1)
  return hash in pages ? (hash as Page) : 'wallet'
}

function App() {
  const [page, setPage] = useState<Page>(pageFromHash)

  useEffect(() => {
    const onHashChange = () => setPage(pageFromHash())
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  return (
    <>
      <nav className="nav">
        {(Object.keys(pages) as Page[]).map((p) => (
          <a key={p} href={`#${p}`} className={p === page ? 'active' : ''}>
            {pages[p]}
          </a>
        ))}
      </nav>
      <ConnectionPanel />
      {page === 'savings' && <SavingsPage />}
    </>
  )
}

function ConnectionPanel() {
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

      {connection.status !== 'connected' && (
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
      )}
    </>
  )
}

export default App
