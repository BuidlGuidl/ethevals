import { encodeFunctionData, parseAbi } from './deps.mjs';
import { governorAbi, localAccounts, proposals, proposalState } from './chain.mjs';
import { rpc } from './rpc.mjs';

const governorViews = parseAbi([
  'function proposalProposer(uint256) view returns (address)',
  'function proposalEta(uint256) view returns (uint256)',
  'function proposalNeedsQueuing(uint256) view returns (bool)',
  'function COUNTING_MODE() view returns (string)',
  'function votingDelay() view returns (uint256)',
  'function votingPeriod() view returns (uint256)',
  'function proposalThreshold() view returns (uint256)',
  'function clock() view returns (uint48)',
]);
const tokenViews = parseAbi([
  'function balanceOf(address) view returns (uint256)',
  'function allowance(address,address) view returns (uint256)',
  'function totalSupply() view returns (uint256)',
  'function decimals() view returns (uint8)',
  'function symbol() view returns (string)',
]);
const voteViews = parseAbi([
  'function getVotes(address) view returns (uint256)',
  'function getPastVotes(address,uint256) view returns (uint256)',
  'function getPastTotalSupply(uint256) view returns (uint256)',
  'function delegates(address) view returns (address)',
  'function numCheckpoints(address) view returns (uint32)',
]);
const timelockViews = parseAbi(['function getMinDelay() view returns (uint256)']);

// The fork loads upstream state lazily, and each journey's revert drops what it loaded.
// Reading the governance views a holder's page uses before the first snapshot keeps that state local.
export async function warmGovernance(url, context, wallet) {
  async function call(address, abi, name, args = []) {
    try { await rpc(url, 'eth_call', [{ to: address, data: encodeFunctionData({ abi, functionName: name, args }) }, 'latest']); }
    catch (error) {
      // Views a contract doesn't have, or timepoints it rejects, revert. Transport failures must stop setup.
      if (error.code !== 3 && !/revert/i.test(error.message)) throw error;
    }
  }
  const holders = [...localAccounts.map(account => account.address), wallet];
  for (const name of ['COUNTING_MODE', 'votingDelay', 'votingPeriod', 'proposalThreshold', 'clock']) {
    await call(context.governor, governorViews, name);
  }
  await call(context.timelock, timelockViews, 'getMinDelay');
  for (const token of [context.token, context.voteToken]) {
    for (const name of ['totalSupply', 'decimals', 'symbol']) await call(token, tokenViews, name);
    for (const holder of holders) await call(token, tokenViews, 'balanceOf', [holder]);
  }
  for (const holder of holders) {
    await call(context.token, tokenViews, 'allowance', [holder, context.voteToken]);
    for (const name of ['getVotes', 'delegates', 'numCheckpoints']) await call(context.voteToken, voteViews, name, [holder]);
  }
  for (const proposal of await proposals(url, context.governor)) {
    const { snapshot } = await proposalState(url, context, proposal);
    for (const name of ['proposalProposer', 'proposalEta', 'proposalNeedsQueuing']) {
      await call(context.governor, governorViews, name, [proposal.id]);
    }
    await call(context.voteToken, voteViews, 'getPastTotalSupply', [snapshot]);
    for (const holder of holders) {
      await call(context.governor, governorAbi, 'hasVoted', [proposal.id, holder]);
      await call(context.governor, governorAbi, 'getVotes', [holder, snapshot]);
    }
  }
}
