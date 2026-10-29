// Actual React component execution with mocked wallet hooks and RPC responses.
// Install react, react-test-renderer, typescript, and viem in a scratch directory.
// VOTING_COMPONENT_DEPS points to that directory; VOTING_APP_SOURCE can select a pre-fix App.tsx.
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const Module = require('node:module')
const { test } = require('node:test')
const dependencies = Module.createRequire(path.resolve(process.env.VOTING_COMPONENT_DEPS, 'package.json'))
const React = dependencies('react')
const { act, create } = dependencies('react-test-renderer')
const ts = dependencies('typescript')
const viem = dependencies('viem')
global.IS_REACT_ACT_ENVIRONMENT = true

const A = '0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
const B = '0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'
const C = '0xcccccccccccccccccccccccccccccccccccccccc'
const context = { chainId: 31337, rpcUrl: 'http://synthetic.invalid',
  token: '0x1111111111111111111111111111111111111111',
  voteToken: '0x2222222222222222222222222222222222222222',
  governor: '0x3333333333333333333333333333333333333333' }
const chain = { id: 31337 }
const unit = 10n ** 18n
const hash = '0x' + '1'.repeat(64)
const logs = [{ args: { proposalId: 42n, description: 'Fee proposal', voteStart: 10n } }]
const source = process.env.VOTING_APP_SOURCE || path.join(__dirname, '../solution/app/src/App.tsx')
function deferred() {
  let resolve, reject
  const promise = new Promise((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}
function text(node) {
  return typeof node === 'string' ? node : (node.children || []).map(text).join('')
}
async function fixture() {
  const state = { account: A, writes: [], reads: [], nextLogs: [], receipt: null }
  const client = {
    getLogs: () => state.nextLogs.shift()?.promise || Promise.resolve(logs),
    getBlockNumber: async () => 20n,
    readContract: async request => {
      state.reads.push(request)
      const holder = request.functionName === 'hasVoted' ? request.args[1] : request.args[0]
      switch (request.functionName) {
        case 'state': return 1
        case 'proposalVotes': return [2n * unit, 3n * unit, 0n]
        case 'proposalDeadline': return 100n
        case 'quorum': return 4n * unit
        case 'hasVoted': return holder === C
        case 'getVotes': return holder === B ? 0n : 7n * unit
        case 'balanceOf': return holder === B ? 0n : request.address === context.token ? 11n * unit : 9n * unit
        default: throw new Error('Unexpected read: ' + request.functionName)
      }
    },
    waitForTransactionReceipt: () => state.receipt?.promise || Promise.resolve({ status: 'success' }),
  }
  const wallet = { writeContract: async request => { state.writes.push(request); return hash } }
  const compiled = ts.transpileModule(fs.readFileSync(source, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020,
      jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true },
  }).outputText
  const component = new Module(source)
  component.require = name => {
    if (name === 'react' || name === 'react/jsx-runtime') return dependencies(name)
    if (name === 'viem') return { ...viem, createPublicClient: () => client }
    if (name === './wagmi') return { tokenChain: chain }
    if (name === '../chain_context.json') return context
    if (name === 'wagmi') return {
      useConnection: () => ({ address: state.account }),
      useConnect: () => ({ connect() {} }), useConnectors: () => [],
      useDisconnect: () => ({ disconnect() {} }), useWalletClient: () => ({ data: wallet }),
    }
    throw new Error('Unexpected component dependency: ' + name)
  }
  component._compile(compiled, source)
  const App = component.exports.default
  let renderer
  await act(async () => { renderer = create(React.createElement(App)) })
  const buttons = label => renderer.root.findAllByType('button').filter(node => text(node) === label)
  const button = label => {
    const matches = buttons(label)
    assert.equal(matches.length, 1, label + ' control exists')
    return matches[0]
  }
  const click = async label => {
    await act(async () => { const control = button(label); if (!control.props.disabled) control.props.onClick() })
  }
  await click('Governance')
  return { state, buttons, button, click,
    view: () => text(renderer.toJSON()),
    switchTo: async account => { state.account = account; await act(async () => renderer.update(React.createElement(App))) },
    close: async () => act(async () => renderer.unmount()),
    amount: async value => act(async () => renderer.root.findByType('input').props.onChange({ target: { value } })),
  }
}
function assertBlocked(page) {
  assert.equal(page.buttons('Vote For').every(node => node.props.disabled === true), true)
  assert.doesNotMatch(page.view(), /Voting power at snapshot: 7/)
  assert.doesNotMatch(page.view(), /TOKEN balance11/)
  assert.doesNotMatch(page.view(), /Wrapped vTOKEN9/)
}
function assertVote(request) {
  assert.deepEqual({ address: request.address, functionName: request.functionName, args: request.args,
    account: request.account, chain: request.chain }, {
    address: '0x3333333333333333333333333333333333333333', functionName: 'castVote',
    args: [42n, 1], account: A, chain: { id: 31337 },
  })
}

test('account switch hides old eligibility and balances during pending and failed reads', async () => {
  const page = await fixture()
  try {
    assert.match(page.view(), /Voting power at snapshot: 7/)
    assert.match(page.view(), /TOKEN balance11/)
    assert.equal(page.button('Vote For').props.disabled, false)
    const pending = deferred()
    page.state.nextLogs.push(pending)
    await page.switchTo(B)
    assertBlocked(page)
    await page.click('Vote For')
    assert.equal(page.state.writes.length, 0)
    await act(async () => pending.reject(new Error('RPC unavailable')))
    assertBlocked(page)
    assert.match(page.view(), /RPC unavailable/)
    await page.switchTo(A)
    await page.click('Vote For')
    assert.equal(page.state.writes.length, 1)
    assertVote(page.state.writes[0])
  } finally { await page.close() }
})

test('zero-weight and already-voted holders receive only their own successful reads', async () => {
  const page = await fixture()
  try {
    const pending = deferred()
    page.state.nextLogs.push(pending)
    await page.switchTo(B)
    assertBlocked(page)
    await act(async () => pending.resolve(logs))
    assert.match(page.view(), /Voting power at snapshot: 0/)
    assert.match(page.view(), /TOKEN balance0/)
    assert.equal(page.button('Vote For').props.disabled, true)
    await page.switchTo(A)
    assert.equal(page.button('Vote For').props.disabled, false)
    const voted = deferred()
    page.state.nextLogs.push(voted)
    await page.switchTo(C)
    assertBlocked(page)
    await act(async () => voted.resolve(logs))
    assert.match(page.view(), /You have voted on this proposal\./)
    assert.equal(page.button('Vote For').props.disabled, true)
    await page.click('Vote For')
    assert.equal(page.state.writes.length, 0)
    await page.switchTo(A)
    await page.click('Vote For')
    assert.equal(page.state.writes.length, 1)
    assertVote(page.state.writes[0])
    const read = page.state.reads.find(row => row.address === context.governor && row.functionName === 'getVotes')
    assert.deepEqual(read.args, [A, 10n])
  } finally { await page.close() }
})

test('confirmed vote stays blocked when its refresh fails', async () => {
  const page = await fixture()
  try {
    const pending = deferred()
    page.state.nextLogs.push(pending)
    await page.click('Vote For')
    assert.equal(page.state.writes.length, 1)
    assertVote(page.state.writes[0])
    await act(async () => pending.reject(new Error('Post-vote read failed')))
    assert.match(page.view(), /Post-vote read failed/)
    assertBlocked(page)
    await page.click('Vote For')
    assert.equal(page.state.writes.length, 1)
  } finally { await page.close() }
})

test('older refresh cannot overwrite a newer account or its error', async () => {
  const page = await fixture()
  try {
    const old = deferred()
    page.state.nextLogs.push(old)
    await page.switchTo(C)
    await page.switchTo(B)
    assert.match(page.view(), /Voting power at snapshot: 0/)
    await act(async () => old.resolve(logs))
    assert.match(page.view(), /Voting power at snapshot: 0/)
    assert.match(page.view(), /TOKEN balance0/)
    assert.doesNotMatch(page.view(), /You have voted/)
    const staleError = deferred()
    page.state.nextLogs.push(staleError)
    await page.switchTo(C)
    await page.switchTo(B)
    await act(async () => staleError.reject(new Error('Old holder error')))
    assert.doesNotMatch(page.view(), /Old holder error/)
    assert.equal(page.button('Vote For').props.disabled, true)
  } finally { await page.close() }
})

test('old transaction completion cannot refresh the current holder with its captured account', async () => {
  const page = await fixture()
  try {
    const receipt = deferred()
    page.state.receipt = receipt
    await page.click('Vote For')
    assertVote(page.state.writes[0])
    await page.switchTo(B)
    assert.match(page.view(), /Voting power at snapshot: 0/)
    await act(async () => receipt.resolve({ status: 'success' }))
    assert.match(page.view(), /Voting power at snapshot: 0/)
    assert.match(page.view(), /TOKEN balance0/)
    assert.doesNotMatch(page.view(), /Transaction confirmed\./)
    assert.equal(page.button('Vote For').props.disabled, true)
  } finally { await page.close() }
})

test('wrapping stops after approval if the holder changes, and completes for an unchanged holder', async () => {
  const page = await fixture()
  try {
    await page.amount('2')
    const receipt = deferred()
    page.state.receipt = receipt
    await page.click('Wrap')
    assert.deepEqual(page.state.writes.map(row => [row.address, row.functionName, row.args, row.account]), [
      [context.token, 'approve', [context.voteToken, 2n * unit], A],
    ])
    await page.switchTo(B)
    await act(async () => receipt.resolve({ status: 'success' }))
    assert.equal(page.state.writes.length, 1)
    assert.match(page.view(), /TOKEN balance0/)
    page.state.receipt = null
    await page.switchTo(A)
    await page.click('Wrap')
    assert.deepEqual(page.state.writes.map(row => [row.address, row.functionName, row.args, row.account]), [
      [context.token, 'approve', [context.voteToken, 2n * unit], A],
      [context.token, 'approve', [context.voteToken, 2n * unit], A],
      [context.voteToken, 'depositFor', [A, 2n * unit], A],
    ])
    assert.match(page.view(), /Transaction confirmed\./)
  } finally { await page.close() }
})
