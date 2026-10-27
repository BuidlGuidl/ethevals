import { useEffect, useState } from 'react'
import { createPublicClient, http, parseAbi, parseUnits, formatUnits } from 'viem'
import type { Address, Hash, WalletClient } from 'viem'
import { useConnect, useConnection, useConnectors, useDisconnect, useWalletClient } from 'wagmi'
import { tokenChain as chain } from './wagmi'
import context from '../chain_context.json'

const client = createPublicClient({ chain, transport: http(context.rpcUrl) })
const abi = parseAbi([
  'function state(uint256) view returns (uint8)',
  'function proposalVotes(uint256) view returns (uint256,uint256,uint256)',
  'function proposalDeadline(uint256) view returns (uint256)',
  'function quorum(uint256) view returns (uint256)',
  'function getVotes(address,uint256) view returns (uint256)',
  'function castVote(uint256,uint8) returns (uint256)',
  'function hasVoted(uint256,address) view returns (bool)',
  'event ProposalCreated(uint256 proposalId,address proposer,address[] targets,uint256[] values,string[] signatures,bytes[] calldatas,uint256 voteStart,uint256 voteEnd,string description)',
])
const tokenAbi = parseAbi([
  'function balanceOf(address) view returns (uint256)', 'function getVotes(address) view returns (uint256)',
  'function approve(address,uint256) returns (bool)', 'function depositFor(address,uint256) returns (bool)',
  'function delegate(address)',
])
function address(text: string): Address {
  if (!/^0x[0-9a-fA-F]{40}$/.test(text)) throw new Error('Invalid contract address')
  return text as Address
}
const governor = address(context.governor)
const token = address(context.token)
const voteToken = address(context.voteToken)
const states = ['Pending', 'Active', 'Canceled', 'Defeated', 'Succeeded', 'Queued', 'Expired', 'Executed']
const format = (amount: bigint) => Number(formatUnits(amount, 18)).toLocaleString('en-US', { maximumFractionDigits: 4 })
type Proposal = { id: bigint; description: string; state: number; for: bigint; against: bigint;
  quorum: bigint; end: bigint; weight: bigint; snapshot: bigint; voted: boolean }

export default function App() {
  const connection = useConnection()
  const account = connection.address
  const { connect } = useConnect()
  const connectors = useConnectors()
  const { disconnect } = useDisconnect()
  const { data: wallet } = useWalletClient({ chainId: chain.id })
  const [page, setPage] = useState('connection')
  const [rows, setRows] = useState<Proposal[]>([])
  const [power, setPower] = useState({ token: 0n, wrapped: 0n, votes: 0n })
  const [amount, setAmount] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  async function refresh(holder = account) {
    const logs = await client.getLogs({ address: governor, event: abi[7], fromBlock: 0n, toBlock: 'latest', strict: true })
    const block = await client.getBlockNumber({ cacheTime: 0 })
    const proposals = await Promise.all(logs.map(async log => {
      const event = log.args
      const [state, tallies, end, quorum, weight, voted] = await Promise.all([
        client.readContract({ address: governor, abi, functionName: 'state', args: [event.proposalId] }),
        client.readContract({ address: governor, abi, functionName: 'proposalVotes', args: [event.proposalId] }),
        client.readContract({ address: governor, abi, functionName: 'proposalDeadline', args: [event.proposalId] }),
        client.readContract({ address: governor, abi, functionName: 'quorum', args: [event.voteStart] }),
        holder && block > event.voteStart ? client.readContract({ address: governor, abi, functionName: 'getVotes', args: [holder, event.voteStart] }) : 0n,
        holder ? client.readContract({ address: governor, abi, functionName: 'hasVoted', args: [event.proposalId, holder] }) : false,
      ])
      return { id: event.proposalId, description: event.description, state, for: tallies[1], against: tallies[0],
        end, quorum, weight, voted, snapshot: event.voteStart }
    }))
    setRows(proposals.reverse())
    if (holder) {
      const [balance, wrapped, votes] = await Promise.all([
        client.readContract({ address: token, abi: tokenAbi, functionName: 'balanceOf', args: [holder] }),
        client.readContract({ address: voteToken, abi: tokenAbi, functionName: 'balanceOf', args: [holder] }),
        client.readContract({ address: voteToken, abi: tokenAbi, functionName: 'getVotes', args: [holder] }),
      ])
      setPower({ token: balance, wrapped, votes })
    }
  }
  useEffect(() => { void refresh().catch(error => setMessage(String(error))) }, [account])
  async function confirmed(hash: Hash) {
    const receipt = await client.waitForTransactionReceipt({ hash })
    if (receipt.status !== 'success') throw new Error('Transaction reverted.')
  }
  async function transaction(run: (wallet: WalletClient, holder: Address) => Promise<void>) {
    if (!account || !wallet) return
    setBusy(true)
    try {
      await run(wallet, account)
      await refresh()
      setMessage('Transaction confirmed.')
    } catch (error) { setMessage(String(error)) }
    finally { setBusy(false) }
  }
  return <main>
    <nav><button onClick={() => setPage('connection')}>Connection</button><button onClick={() => setPage('governance')}>Governance</button></nav>
    <h2>Connection</h2>
    {account ? <p>{account} <button onClick={() => disconnect()}>Disconnect</button></p>
      : connectors.map(connector => <button key={connector.uid} onClick={() => connect({ connector })}>{connector.name}</button>)}
    {page === 'governance' && <>
    <h1>Governance</h1>
    <section><h2>Voting power</h2>
      <dl><dt>TOKEN balance</dt><dd>{format(power.token)}</dd>
        <dt>Wrapped vTOKEN</dt><dd>{format(power.wrapped)}</dd>
        <dt>Your votes</dt><dd>{format(power.votes)}</dd></dl>
      {power.wrapped > 0n && power.votes === 0n && <p>Your wrapped tokens do not count as votes yet. Delegate to yourself to vote.</p>}
      <div><h3>Wrap TOKEN</h3><input aria-label="Wrap amount" value={amount} onChange={event => setAmount(event.target.value)} />
        <button disabled={!wallet || busy || !amount} onClick={() => void transaction(async (wallet, holder) => {
          const value = parseUnits(amount, 18)
          const approval = await wallet.writeContract({ account: holder, chain, address: token, abi: tokenAbi, functionName: 'approve', args: [voteToken, value] })
          await confirmed(approval)
          const deposit = await wallet.writeContract({ account: holder, chain, address: voteToken, abi: tokenAbi, functionName: 'depositFor', args: [holder, value] })
          await confirmed(deposit)
        })}>Wrap</button></div>
      <button disabled={!wallet || busy} onClick={() => void transaction(async (wallet, holder) => {
        const hash = await wallet.writeContract({ account: holder, chain, address: voteToken, abi: tokenAbi, functionName: 'delegate', args: [holder] })
        await confirmed(hash)
      })}>Activate voting power</button>
    </section>
    <p role="status">{message}</p>
    <h2>Proposals</h2>
    {rows.map(proposal => <article key={proposal.id.toString()}>
      <h3>{proposal.description}</h3><p>{states[proposal.state]}</p>
      <dl><dt>For</dt><dd>{format(proposal.for)}</dd><dt>Against</dt><dd>{format(proposal.against)}</dd></dl>
      <p>Quorum: {format(proposal.for)} / {format(proposal.quorum)} {proposal.for >= proposal.quorum ? 'reached' : 'not reached'}</p>
      <p>Voting ends at block {proposal.end.toLocaleString('en-US')}</p>
      {account && <p>Voting power at snapshot: {format(proposal.weight)}</p>}
      {proposal.voted && <p>You have voted on this proposal.</p>}
      {proposal.state === 1 && account && [1, 0].map(support => <button key={support}
        disabled={!wallet || busy || proposal.weight === 0n || proposal.voted} onClick={() => void transaction(async (wallet, holder) => {
          const hash = await wallet.writeContract({ account: holder, chain, address: governor, abi, functionName: 'castVote', args: [proposal.id, support] })
          await confirmed(hash)
        })}>Vote {support ? 'For' : 'Against'}</button>)}
    </article>)}</>}
  </main>
}
