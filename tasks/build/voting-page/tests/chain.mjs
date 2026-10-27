import fs from 'node:fs/promises';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { parseAbi, decodeEventLog, decodeFunctionResult, encodeFunctionData, decodeFunctionData } from './deps.mjs';
import { rpc, read, send } from './rpc.mjs';

export const UNIT = 10n ** 18n;
export const governorAbi = parseAbi([
  'function state(uint256) view returns (uint8)',
  'function proposalVotes(uint256) view returns (uint256 againstVotes,uint256 forVotes,uint256 abstainVotes)',
  'function proposalSnapshot(uint256) view returns (uint256)',
  'function proposalDeadline(uint256) view returns (uint256)',
  'function quorum(uint256) view returns (uint256)',
  'function getVotes(address,uint256) view returns (uint256)',
  'function castVote(uint256,uint8) returns (uint256)',
  'function castVoteWithReason(uint256,uint8,string) returns (uint256)',
  'function castVoteWithReasonAndParams(uint256,uint8,string,bytes) returns (uint256)',
  'function propose(address[],uint256[],bytes[],string) returns (uint256)',
  'event ProposalCreated(uint256 proposalId,address proposer,address[] targets,uint256[] values,string[] signatures,bytes[] calldatas,uint256 voteStart,uint256 voteEnd,string description)',
  'event VoteCast(address indexed voter,uint256 proposalId,uint8 support,uint256 weight,string reason)',
  'event VoteCastWithParams(address indexed voter,uint256 proposalId,uint8 support,uint256 weight,string reason,bytes params)',
]);
export const votesAbi = parseAbi([
  'function getVotes(address) view returns (uint256)',
  'function depositFor(address,uint256) returns (bool)',
  'function delegate(address)',
  'event DelegateChanged(address indexed delegator,address indexed fromDelegate,address indexed toDelegate)',
]);
export let localAccounts = [];
export async function discoverAccounts(url, context) {
  const initial = await proposals(url, context.governor);
  const ordinary = initial.find(p => p.description === 'Set the protocol fee to 6 basis points');
  if (!ordinary) throw new Error('Ordinary executed proposal was not found');
  const logs = await rpc(url, 'eth_getLogs', [{ address: context.voteToken, fromBlock: '0x0', toBlock: 'latest' }]);
  const holders = logs.flatMap(log => {
    try { const event = decodeEventLog({ abi: votesAbi, ...log });
      return event.eventName === 'DelegateChanged' ? [event.args.delegator] : [];
    } catch { return []; }
  });
  localAccounts = [ordinary.proposer, ...new Set(holders)].slice(0, 5).map(address => ({ address, type: 'json-rpc' }));
  if (localAccounts.length !== 5) throw new Error('Could not find four seeded holders');
  return { initial, ordinary };
}
export async function value(url, address, abi, name, args = []) {
  return decodeFunctionResult({ abi, functionName: name, data: await read(url, address, abi, name, args) });
}
export async function proposals(url, governor) {
  const logs = await rpc(url, 'eth_getLogs', [{ address: governor, fromBlock: '0x0', toBlock: 'latest' }]);
  return logs.flatMap(log => {
    try {
      const event = decodeEventLog({ abi: governorAbi, ...log });
      return event.eventName === 'ProposalCreated' ? [{ ...event.args, id: event.args.proposalId }] : [];
    } catch { return []; }
  });
}
export async function prepareFork(url, context, output) {
  const { ordinary } = await discoverAccounts(url, context);
  const [deployer, ...holders] = localAccounts.map(account => ({ address: account.address, key: account.address }));
  const fixture = { deployer, holders, protocol: ordinary.targets[0], proposals: {} };
  const program = `import sys,json\nsys.path.insert(0,sys.argv[1])\nimport seed\nurl,context,fixture=json.load(sys.stdin)\nseed.rpc(url,'anvil_setBlockTimestampInterval',[12])\nseed.seed_proposals(url,context,fixture,checks=True)\nfixture['checksBlock']=int(seed.rpc(url,'eth_blockNumber'),16)\nprint(json.dumps(fixture))`;
  const result = await new Promise((resolve, reject) => {
    const child = spawn('python3', ['-c', program, fileURLToPath(new URL('.', import.meta.url))], { timeout: 1200_000 });
    let stdout = '', stderr = '';
    child.stdout.on('data', data => { stdout += data; });
    child.stderr.on('data', data => { stderr += data; });
    child.on('error', reject);
    child.on('close', code => code === 0 ? resolve(stdout) : reject(new Error(`Fixture setup failed: ${stderr}`)));
    child.stdin.end(JSON.stringify([url, context, fixture]));
  });
  await fs.writeFile(path.join(output, 'seed.log'), result);
  return JSON.parse(result);
}
export function requestedCalls(wallet, address, abi) {
  return wallet.requests.flatMap(request => {
    const calls = request.method === 'wallet_sendCalls' ? request.params[0].calls
      : /^(?:eth|wallet)_sendTransaction$/.test(request.method) ? [request.params[0]] : [];
    return calls.flatMap(call => {
      if (call.to?.toLowerCase() !== address.toLowerCase()) return [];
      try { return [decodeFunctionData({ abi, data: call.data || call.input })]; } catch { return []; }
    });
  });
}
export const voteRequests = (wallet, governor, id) => requestedCalls(wallet, governor, governorAbi)
  .filter(call => /^castVote/.test(call.functionName) && call.args[0] === id);
export function executedCalls(wallet, address, abi, name) {
  return wallet.transactions.flatMap(tx => {
    if (tx.call?.to?.toLowerCase() !== address.toLowerCase() || tx.receipt.status !== '0x1') return [];
    try { const decoded = decodeFunctionData({ abi, data: tx.call.data || tx.call.input });
      return decoded.functionName === name ? [{ hash: tx.hash, ...decoded }] : [];
    } catch { return []; }
  });
}
export async function mineTo(url, end) {
  let block = Number(await rpc(url, 'eth_blockNumber'));
  while (block < end) {
    const count = Math.min(1000, end - block);
    await rpc(url, 'anvil_mine', ['0x' + count.toString(16), '0xc']);
    block += count;
  }
}
export async function proposalState(url, context, proposal) {
  const id = proposal.id;
  const [state, tallies, end, snapshot] = await Promise.all([
    value(url, context.governor, governorAbi, 'state', [id]),
    value(url, context.governor, governorAbi, 'proposalVotes', [id]),
    value(url, context.governor, governorAbi, 'proposalDeadline', [id]),
    value(url, context.governor, governorAbi, 'proposalSnapshot', [id]),
  ]);
  return { state: Number(state), against: tallies[0], for: tallies[1], end, snapshot,
    quorum: await value(url, context.governor, governorAbi, 'quorum', [snapshot]) };
}
export function voteEvents(wallet, governor, voter, proposalId) {
  return wallet.transactions.flatMap(tx => tx.receipt.logs.flatMap(log => {
    if (log.address.toLowerCase() !== governor.toLowerCase()) return [];
    try {
      const event = decodeEventLog({ abi: governorAbi, ...log });
      return /^VoteCast/.test(event.eventName) && event.args.proposalId === proposalId
        && event.args.voter.toLowerCase() === voter.toLowerCase() ? [{ hash: tx.hash, ...event.args }] : [];
    } catch { return []; }
  }));
}
export async function createProposal(url, context, fixture) {
  const description = 'Set the protocol fee to 23 basis points';
  const tx = await send(url, localAccounts[0], { to: context.governor,
    data: encodeFunctionData({ abi: governorAbi, functionName: 'propose',
      args: [[fixture.protocol], [0n], ['0x69fe0e2d' + (23n).toString(16).padStart(64, '0')], description] }) });
  const event = tx.receipt.logs.map(log => {
    try { return decodeEventLog({ abi: governorAbi, ...log }); } catch { return null; }
  }).find(event => event?.eventName === 'ProposalCreated');
  if (!event) throw new Error('Fixture proposal did not emit ProposalCreated');
  await mineTo(url, Number(event.args.voteStart) + 1);
  return { ...event.args, id: event.args.proposalId };
}
