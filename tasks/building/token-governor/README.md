# Token governor

A protocol team wants holders of its live ERC-20 to control its treasury and protocol owner role.
The task checks whether the governor measures quorum against TOKEN and keeps control behind a two-day wait.
It also checks late votes and the interfaces that Snapshot uses.

## The instruction

```text
our token TOKEN is live, a plain ERC-20 with a fixed 100M supply, and we can't change it. we want our treasury and the owner role on our protocol contract under token holder control. a proposal passes when at least 4% of the supply votes for it, with more for than against, then waits two days before anyone can execute it. our delegates vote through snapshot, so it has to be a standard governor, and our frontend's wrap flow talks to the vote token through src/interfaces/IVoteToken.sol. put the governor in src/TokenGovernor.sol as TokenGovernor, and a deploy script in script/Deploy.s.sol whose run(token) returns the governor address and the address we should move the protocol's ownership and the treasury to. foundry, solidity 0.8.30.
```

## What it touches

- Wrapping a live token. TOKEN has no vote history, so holders deposit it for vote tokens and delegate their votes. Quorum must use TOKEN's fixed supply. The wrapper's supply includes only holders who chose to wrap.
- Control of money and owner calls. The contract that enforces the wait must hold both. Giving the governor the protocol owner role lets it bypass that wait.
- Time to answer late votes. If the vote first reaches quorum near its deadline, other holders need time to respond.
- Snapshot integration. The governor and vote token expose standard interfaces. Voting power comes from the proposal's snapshot, so a holder cannot buy votes after seeing a live proposal.

## The checks

The environment contains TOKEN, Protocol, and the vote token interface in a Foundry project on Solidity 0.8.30.
The verifier deploys TOKEN and Protocol, calls the agent's deploy script, and drives the result through public interfaces.
Each test is one check. The reward is 1 only when every check passes.

| Check | What it proves | Area |
| --- | --- | --- |
| `compile` | The tests and the agent's contracts compile together | all |
| `test_quorumCountsTheWholeSupply` | One million for-votes fail; five million pass and execute. Exactly four million for-votes pass, and equal for and against votes fail | quorum |
| `test_theDelayGuardsTheMoney` | The protocol's owner is a contract other than the governor, direct owner calls revert, and treasury payments and protocol calls execute only after two days | control |
| `test_lateVotesExtendTheVote` | Crossing quorum in the last hour extends the deadline and leaves the proposal active at its former deadline | late votes |
| `test_snapshotCanRunIt` | Standard governor and historical vote views work; votes acquired after the snapshot cannot pass that proposal | Snapshot |

## Why it matters

Opt-in wrapping can shrink quorum far below the share of TOKEN that the team meant.
The [OpenZeppelin quorum module](https://github.com/OpenZeppelin/openzeppelin-contracts/blob/v5.7.0/contracts/governance/extensions/GovernorVotesQuorumFraction.sol#L63) reads the vote token's historical supply.
[Nexus Mutual](https://nexusmutual.io/blog/term-finance-governance-takeover-incident-report) and [rekt](https://rekt.news/term-labs-rekt) report that Term Labs lost $8.47M after an attacker cleared quorum against wrapped supply.

The contract that holds the owner role controls the protocol as well as the treasury.
The [Moonwell governance attack](https://www.theblock.co/news/defi/2026-03-26-moonwell-governance-attack-395272) shows why admin calls belong behind the same wait.
A timelock that reads its delay at execution lets one vote shorten every wait behind it.
The [Zodiac delay contract](https://github.com/zodiaceco/zodiac-modifier-delay/blob/main/contracts/Delay.sol#L217) illustrates the risk of reading the current delay at execution.

Late quorum gives other voters little time to answer.
The [Compound Foundation's account](https://www.comp.xyz/t/recent-governance-activity-in-context-the-record-since-2024/8120) describes proposal 289 and a burst of votes near its deadline.
The [OpenZeppelin Wizard](https://github.com/OpenZeppelin/contracts-wizard/blob/master/packages/core/solidity/src/governor.ts) does not offer late-quorum protection by default.
The [ENS discussion of Tally's shutdown](https://discuss.ens.domains/t/tally-is-shutting-down-option-to-maintain-the-existing-interface-no-contract-changes/22042) also shows why delegates need standard interfaces that other clients can use.

## Notes

- OpenZeppelin Contracts 5.7.0 is vendored during the image build. A real builder's repository already has its dependencies. This version also includes the [timelock execution fix](https://github.com/OpenZeppelin/openzeppelin-contracts/pull/6386).
- There is no chain sidecar or RPC dependency. Forge advances the governor's chosen clock and uses seconds for the execution wait.
- The tests read voting settings and deadlines from the governor. They accept block-number and timestamp clocks.
- The deploy script runs in-process without a prank. The tests hand Protocol's ownership and the treasury to the holder address it returns.
- The checks set `PRIVATE_KEY` and `DEPLOYER_PRIVATE_KEY` to Anvil's first account key so scripts that read a key do not fail.
