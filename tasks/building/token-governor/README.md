# Token governor

A protocol team's token is live and plain, and they want token holders rather than the team to control the treasury and the protocol's owner role.
The message is the one any token team eventually sends: a quorum, a majority rule, a wait before execution, Snapshot for the delegates, and the wrap flow the frontend already uses.
Hidden Forge tests then check the four things a governor that moves money has to get right, none of which the message spells out.

Governance is where a request looks simplest and the stakes are highest.
The contracts are OpenZeppelin's, the Wizard writes them in a minute, and the result holds every dollar the protocol has.
It is easy to ship a governor that takes proposals and counts votes.
It is harder to ship one the team can safely hand the treasury to.
This task checks the gap.

## The instruction

```text
our token TOKEN is live, a plain ERC-20 with a fixed 100M supply, and we can't change it. we want our treasury and the owner role on our protocol contract under token holder control. a proposal passes when at least 4% of the supply votes for it, with more for than against, then waits two days before anyone can execute it. our delegates vote through snapshot, so it has to be a standard governor, and our frontend's wrap flow talks to the vote token through src/interfaces/IVoteToken.sol. put the governor in src/TokenGovernor.sol as TokenGovernor, and a deploy script in script/Deploy.s.sol whose run(token) returns the governor address and the address we should move the protocol's ownership and the treasury to. foundry, solidity 0.8.30.
```

## What it touches

The instruction leaves out four things. Each has a real incident or an adopted fix behind it, and each is one check.

- **Which supply the quorum counts.** TOKEN has no vote history, so holders wrap it for a vote token and delegate. OpenZeppelin's quorum module measures a share of the vote token's supply, which is only what people have chosen to wrap. "4% of the supply" quietly becomes 4% of whatever is wrapped today. Term Labs lost $8.47M this way in August 2026, and the module's docs never say so.

  ```text
  TOKEN supply          100,000,000   the team's 4%            = 4,000,000 votes
  wrapped so far          5,000,000   the module's 4%          =   200,000 votes
  one holder votes for    1,000,000   passes against the wrapper, fails against TOKEN
  ```

- **Who holds the keys.** The contract that enforces the two-day wait has to own the protocol and hold the treasury. Make the governor itself the owner and a passed proposal can change fees or move funds with no wait at all. The wait also has to be fixed when a proposal is queued, or one vote can shorten every wait behind it. Term's first transaction set its delay to zero, and Moonwell's attacker in March 2026 went straight for the admin rights.

- **Time to answer a late vote.** A proposal can sit at zero votes all week, look dead, and reach quorum in its last hour. If the deadline does not move, the other 96% of holders never get a turn, and the two-day wait does not help because stopping a passed proposal needs another vote. Compound's proposal 289 passed after 18 wallets cast 536,376 COMP in a 23-minute burst at the end of the vote.

  ```text
  day 0 ──────────────────────────────── day 7
  votes   0 ........................... 0 │ 4M for, cast in the last hour
                                          └ closes. 4% spoke. 96% never got a turn.

  with the extension
  votes   0 .................... 4M for │ deadline moves out │ 30M against → defeated
  ```

- **The standard surface.** Delegates vote through Snapshot and the frontend wraps through `IVoteToken`. Both need the standard governor and vote-token views: who delegates to whom, past votes and past supply at a snapshot, and one-to-one withdrawal. A governor that only works through its own frontend fails the team's actual setup. Snapshot voting also means voting power is read at the proposal's snapshot, so nobody can buy votes after seeing a live proposal.

## The checks

The agent starts with TOKEN, Protocol, the `IVoteToken` interface, a `foundry.toml`, and OpenZeppelin 5.7.0 in `lib/`.
The verifier deploys TOKEN and Protocol, runs the agent's deploy script the way `forge script` would, hands the protocol's ownership and 3 ETH to the address the script returns, and drives the governor through the standard interface in [`TokenGovernor.t.sol`](tests/TokenGovernor.t.sol).
It reads the agent's clock mode and voting settings instead of dictating them, so an OpenZeppelin governor on blocks or timestamps, or a custom one that follows the standard, can pass.
Each test is one idea, and the reward is 1 only when every check passes.

| Check | What it proves | Area |
| --- | --- | --- |
| `compile` | The tests and the agent's contracts compile together | all |
| `test_quorumCountsTheWholeSupply` | One million for-votes fail; five million pass and execute. Exactly four million for-votes pass, and equal for and against votes fail | quorum |
| `test_theDelayGuardsTheMoney` | The protocol's owner is a contract other than the governor, direct owner calls revert, and treasury payments and protocol calls execute only after two days | control |
| `test_lateVotesExtendTheVote` | Crossing quorum in the last hour extends the deadline and leaves the proposal active at its former deadline | late votes |
| `test_snapshotCanRunIt` | Standard governor and historical vote views work; votes acquired after the snapshot cannot pass that proposal | Snapshot |

A score of 0 says the agent carried some of the four ideas but not all. The per-check record says which, and that record is what the board learns from.

## Why it matters

Quorum against the wrong supply has already cost money.
The [OpenZeppelin quorum module](https://github.com/OpenZeppelin/openzeppelin-contracts/blob/v5.7.0/contracts/governance/extensions/GovernorVotesQuorumFraction.sol#L63) reads the vote token's historical supply.
[Nexus Mutual](https://nexusmutual.io/blog/term-finance-governance-takeover-incident-report) and [rekt](https://rekt.news/term-labs-rekt) report that Term Labs lost $8.47M after an attacker cleared quorum against the wrapped supply.

Control behind the wait is the difference between a slow loss and a fast one.
The [Moonwell attack](https://www.theblock.co/news/defi/2026-03-26-moonwell-governance-attack-395272) in March 2026 bought $1,800 of tokens, reached quorum in 11 minutes, and would have moved admin of seven markets and the oracle; it was [cancelled before the vote closed](https://forum.moonwell.fi/t/governance-notice-unverified-proposal-on-moonriver-mip-r39/2143) with $1.08M at risk.
The [Zodiac delay contract](https://github.com/zodiaceco/zodiac-modifier-delay/blob/main/contracts/Delay.sol#L217) reads its delay at execution, which is how Term's first transaction removed the wait.

Late votes have not cost money yet, and the record shows why that is luck rather than safety.
The [Compound Foundation's account](https://www.comp.xyz/t/recent-governance-activity-in-context-the-record-since-2024/8120) of proposal 289 in 2024: $24M in COMP, passed 682,191 to 633,636 with 57 voters after 18 wallets cast 536,376 COMP in the last 23 minutes.
It was undone two days later by a [private deal](https://cointelegraph.com/news/golden-boys-behind-compound-governance-attack-agree-to-rescind-proposal), not by the system.
Compound created a proposal guardian eleven days later, and its [current governor](https://github.com/compound-finance/compound-governance/blob/main/contracts/CompoundGovernor.sol) builds in the late-quorum extension.
The [OpenZeppelin Wizard](https://github.com/OpenZeppelin/contracts-wizard/blob/master/packages/core/solidity/src/governor.ts) still does not offer it, so the default path to a governor leaves the hole open.

Standard interfaces outlive the frontends.
The [ENS discussion of Tally's shutdown](https://discuss.ens.domains/t/tally-is-shutting-down-option-to-maintain-the-existing-interface-no-contract-changes/22042) shows delegates moving clients with no contract changes, which only works for a governor that speaks the standard.

## Notes

- Every agent can fail this task and the task still earns its place. The bar here is what a strong agent misses when nobody names the thing. In the first trials on 2026-10-24, Opus 5.5, GPT-6.1-sol and Kimi K3 each passed the quorum, control and Snapshot checks and left the vote open to a last-hour swing; a separate Kimi run measured quorum against the wrapped supply, the design Term shipped. Each check has a design behind it that a model actually produced, so a 0 is a finding, not noise. The day an agent protects the vote without being asked, this task is the one that shows it.
- The checks accept any design that follows the standard. They read the clock mode and voting settings from the governor, accept block numbers or timestamps, any extension length, and any revert reason. They never name a constructor or a library.
- OpenZeppelin Contracts 5.7.0 is in `lib/` when the agent starts, so nothing needs installing.
- There is no chain sidecar or RPC dependency. Forge advances the governor's chosen clock and uses seconds for the execution wait.
- The checks run the deploy script the way `forge script` does and set `PRIVATE_KEY` and `DEPLOYER_PRIVATE_KEY`, so an ordinary script works unchanged.
