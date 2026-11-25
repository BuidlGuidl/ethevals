# Leaked deployer key

A team's deployer key was public for an hour. They ask the agent to take away everything that key can do right now and hand it to their 2-of-3 Safe, whose other two signers are away until tomorrow.
The task checks that the key is powerless when the agent stops, that the Safe only has to accept, and that the agent noticed someone had already used the key: the key queued an upgrade that is still waiting in the timelock, and a stranger's address holds timelock roles.

## The instruction

> our deployer key sat in a public repo for about an hour before we noticed. make sure that key can't do anything to our contracts anymore, and hand everything it controlled to our safe. the safe is 2 of 3, and the other two signers are offline until tomorrow. this can't wait for them: the key has to be dead when you're done, and tomorrow we'll sign whatever the safe still has to accept. the contract addresses, the deployer key and one safe signer's key are in chain_context.json, and this repo is what we deployed from. do it on that chain and tell us what you did and what's left for us to sign.

## What it touches

The team did the careful thing. Upgrades, the treasury, and the token's roles sit behind an OpenZeppelin `TimelockController` with a two-day delay, so a stolen key cannot take funds at once.
The instruction names no power and says nothing about anyone having used the key.

- **The timelock seat.** The deploy script makes the deployer the only proposer. The constructor also makes every proposer a canceller, and the script passes the deployer as the optional admin and never renounces it. The key holds three roles, and the script shows one line. The Safe has to get the proposer and canceller roles before the key gives up the admin role, or nobody is left who can propose.
- **What was done with the key.** Forty minutes before the agent starts, the key granted the proposer and admin roles to an unknown address. That address deployed a contract that is not in the repo, and the key queued an upgrade of Staking to it. The upgrade becomes executable two days later, and the deploy script lets anyone execute. Removing the key's own roles stops none of this. The queued operation has to be cancelled, and the stranger's roles revoked, while the key still holds the canceller and admin roles.
- **Two-step ownership with nobody to accept.** The key owns Staking directly, to tune the reward rate under a cap. Staking is `Ownable2Step`, so after `transferOwnership(safe)` the key is still the owner until the Safe accepts, and the Safe cannot sign today. Someone the team trusts has to accept first and offer Staking on to the Safe. The one signer key the agent holds can do that, and so can a small contract.
- **A role the script forgot.** The token's constructor makes its first admin a pauser. The script moves the admin role to the timelock and leaves the pauser role on the key. The key can only renounce it, because the token's admin is now the timelock.
- **Everything else.** The timelock keeps its delay, its open execution, and what it owns. Staking keeps its minter role and its code, the guardian keeps the pauser role, and two accounts have TOKEN staked.

## The checks

The chain starts fresh, with its clock nine days back.
Setup repeats the repo's [deploy script](environment/repo/script/Deploy.s.sol) with a new random deployer key, creates a 2-of-3 Safe 1.4.1, and lays out nine days of history: two accounts stake, and the team pays a grant from the treasury through the timelock.
Forty minutes before the end, the key grants timelock roles to a stranger, who deploys [their own implementation](environment/setup/StakingBackdoor.sol). The key then queues the upgrade to it.
The agent starts with the repo, OpenZeppelin 5.7.0 in `lib/`, and `chain_context.json` with the addresses, the deployer key, and one Safe signer's key. One signer cannot execute a Safe transaction.
The [tests](tests/KeyRotation.t.sol) fork the chain the agent leaves. They act as the leaked key, as the stranger, as anyone three days later, as the Safe, and as a staker.

| Check | What it proves | Area |
| --- | --- | --- |
| `compile` | The tests compile | all |
| `test_keyHasNoTimelockRoles` | "The key has to be dead when you're done": the key holds no proposer, canceller, or admin role on the timelock, and it can neither schedule an operation nor grant a role | timelock |
| `test_keyHasNoTokenRoles` | Same sentence: the key holds no token role and cannot pause | token roles |
| `test_keyDoesNotOwnStaking` | Same sentence: the key is neither owner nor pending owner of Staking, and cannot set the reward rate | ownership |
| `test_queuedUpgradeCannotRun` | "Make sure that key can't do anything to our contracts anymore": three days later the stranger and a passer-by both try to execute the upgrade the key queued, and Staking still runs its original code | queued operations |
| `test_safeGetsEveryPower` | "Hand everything it controlled to our safe": the Safe holds the proposer and canceller roles. It owns Staking, or is its pending owner and becomes owner with one `acceptOwnership`. Acting as the Safe, the test sets the reward rate, then schedules, cancels, and after the delay executes timelock operations on the treasury, the token, and Staking's code | handover |
| `test_thiefHasNoRoles` | The address that got roles through the key holds no proposer, canceller, or admin role on the timelock, and can neither schedule an operation nor grant a role | planted access |
| `test_nothingElseChanged` | The timelock keeps its two-day delay, open execution, the token's admin role, the `ProxyAdmin`, and the Treasury with its balance. Staking keeps its code, reward rate, and minter role, the guardian keeps the pauser role, the token is not paused, the Safe's owners and threshold are as before, and a staker can claim a day's reward and unstake | scope |

The first five are gate checks, because the instruction asks for them.
`test_thiefHasNoRoles` and `test_nothingElseChanged` are judgment checks. The instruction speaks only of the key, and an experienced developer also looks at what the key did while it was public and leaves the rest alone.

## Why it matters

A deployer key that still holds upgrade rights is a known way to lose a protocol.
In March 2025 an attacker got the key behind Zoth's deployer address, upgraded a proxy to their own code, and took about $8.4 million. [Halborn](https://www.halborn.com/blog/post/explained-the-zoth-hack-march-2025) and [Rekt](https://rekt.news/zoth-rekt) describe it.

A key in a public repo is found fast.
In June 2024 a developer made a repository public with a wallet key in it and [lost about $40,000](https://cointelegraph.com/news/web3-dev-loses-40k-github-key-leak). He said the funds left within two minutes.
A multisig is slower than that, so the key has to lose its powers before the signers are back.

Access an attacker grants to their own address outlives the first response.
In February 2024 an attacker added themselves as a minter on PlayDapp's token and minted twice, on February 9 and again on February 12. [Halborn](https://www.halborn.com/blog/post/explained-the-playdapp-hack-february-2024) describes it.

A timelock is what gives a team the two days.
OpenZeppelin's [governance guide](https://docs.openzeppelin.com/contracts/5.x/governance) says a timelock "allows users to exit the system if they disagree with a decision before it is executed".
The time only helps if someone reads the queue and cancels.

Each power the script does not show follows from how the library works.

- OpenZeppelin's [governance docs](https://docs.openzeppelin.com/contracts/5.x/api/governance) say "the proposers are in charge of scheduling (and cancelling) operations", and that the optional admin "should renounce its role such that all further maintenance operations have to go through the timelock process".
- The [access docs](https://docs.openzeppelin.com/contracts/5.x/api/access) say that with `Ownable2Step` "the new owner must call Ownable2Step.acceptOwnership in order to replace the old one". Until then the old owner keeps every right, including starting a different transfer.
- The same page says `AccessControl` "doesn't allow enumerating role members except through off-chain means by accessing the contract event logs". So a role granted through the key shows up only to someone who reads the events.

## Notes

- The solution cancels every pending timelock operation, since nothing the team queued is still waiting. It revokes timelock roles from every address the deploy script did not name, and grants the Safe the proposer and canceller roles. For Staking, the key transfers ownership to the Safe signer, who accepts and offers it to the Safe. The key renounces the token's pauser role, then its timelock roles, admin last.
- The checks do not say who may hold Staking overnight. Any owner other than the leaked key passes, as long as the Safe is the pending owner.
- The Safe may hold the timelock's admin role or not. The timelock administers itself either way.
- The Safe does not need the token's pauser role. It can grant it to itself through the timelock.
- The key holds no TOKEN. ETH left on it is not checked, since the key needs it for gas.
- The checks do not look at operations the agent itself queues in the timelock. In one trial an agent used the key to queue a pauser-role grant to the Safe before the key gave up its roles.
- In the first trials Fable 5.2, Opus 5.5, and GPT-6.2 Sol each passed every check. In one of its two trials GPT-6.2 Sol also took the executor role from the zero address and gave it to the Safe, which fails `test_nothingElseChanged`. No open model has run yet.
- Setup sends every transaction through anvil directly, so it can move the clock between them. It repeats the deploy script's steps instead of running it, and compiles with the repo's compiler settings.
- A fresh chain has no Safe contracts. Setup compiles Safe 1.4.1 from its tagged source with Solidity 0.8.30 and deploys it, so the singleton and factory addresses are not the mainnet ones.
- The task needs no RPC secret.
