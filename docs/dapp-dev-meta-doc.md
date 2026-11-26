# How we find and shape tasks

This doc is for people and agents writing tasks for ETH Evals. It shares how we think about tasks, what makes one worth keeping, and a light path from an idea to a pull request. It is a guide for taste, not a rigid checklist.

ETH Evals tests practical Ethereum, meaning how well agents build, act, and make real-world calls when working with Ethereum. We are past testing whether a model knows basic Solidity or can follow a detailed spec. What separates models now is judgment.

## The three pillars

Each task sits in one pillar and stands on its own. You do not need to bundle Concepts tasks with a Build or Act task.

- **Concepts.** A question with a fixed answer or judge criteria. It checks practical Ethereum knowledge and reasoning, especially where a bare model with no web gets it wrong.
- **Build.** The agent starts in an environment and writes code: contracts, a frontend, scripts, or an audit report. The verifier checks what it wrote.
- **Act.** The agent sends real transactions on a chain, usually a mainnet fork, and the verifier checks what changed onchain (balances, receipts, approvals, protocol state).

For Act tasks, it is fine for the instruction to say the chain is a fork. Frontier models often refuse real-looking mainnet transactions out of caution, and saying it is a fork avoids false refusals while keeping the rest of the task realistic.

## What makes a task worth keeping

### Practical Ethereum and real-world judgment

Latest open models are strong at tactical checks and textbook patterns. Short bug snippets, isolated trivia, and tightly specified instructions rarely separate models anymore.

Good tasks test judgment, meaning the calls an experienced Ethereum developer makes without being told. For example:

- In a Build task, does the frontend handle network switching when sending a transaction, or does a governor handle Snapshot delegates and wrapping cleanly ([`token-governor`](../tasks/build/token-governor/))?
- In an Act task, does the agent notice the biggest pools are mispriced before selling 400 ETH ([`treasury-eth-sale`](../tasks/act/treasury-eth-sale/)), or check pending cap raises before exiting a vault?
- In a security or audit task (filed under Build for now), can the agent audit a real codebase and tell an exploitable bug from code that looks like a famous exploit but is already patched?

### The instruction reads like a real user

Write the instruction the way a real user would send it: a developer asking for an app, an operator asking to rebalance a vault, or a team asking for a pre-launch audit. Say what they want, why, and the few details they would naturally include, such as where files go or that they are running on a fork.

Leave the rest to the agent. If every agent would build something incompatible, the instruction is too loose. If it lists every function and edge case, it becomes a spec, and a spec only tests instruction following.

For every check, point to the sentence in the instruction that failing work breaks, read as a careful user would read it. If the person asking would say "that's not what I asked for", the check is fair even when hidden. If they would say "I should have asked for that", fix the instruction, not the check.

### The bar

A task is worth keeping when either a frontier model fails it, or at least two open models fail it, for a real practical-Ethereum reason rather than a trick or ambiguous wording. The active agents and models live in [`runner/ethevals/job.yaml`](../runner/ethevals/job.yaml).

Only a trial proves whether a task meets this bar. A past incident or audit report is a good reason to try an idea, not proof that current models will fail it.

A few quick questions to sanity-check an idea:

- Would an experienced reviewer block a merge or stop a transaction over this?
- Does it test real-world judgment rather than pattern matching?
- Does it reflect how Ethereum is used today?

## Where ideas come from

Start from whichever door fits best:

- **Your own Ethereum work.** Things you built, sent onchain, got wrong, or had to debug in production. War stories make the best tasks, especially for Act.
- **Live mainnet protocols and incidents.** Reading how real apps work on Ethereum mainnet, what their libraries warn about in comments, and what went wrong in audits or post-mortems.
- **The map below.** Optional inspiration when you want to see areas we have not covered yet.

Before writing checks, scan the existing tasks in [`tasks/`](../tasks/) and [open pull requests](https://github.com/BuidlGuidl/ethevals/pulls) so we do not duplicate what is already covered.

## From idea to pull request

1. **Share the rough idea first.** Write a few lines on who is asking, what they want done, and where you expect agents to fail. Align on the idea with the team before building the full task.
2. **Build the task folder.** Read [CONTEXT.md](../CONTEXT.md) for the repo's vocabulary and [Add a task](add-a-task.md) for the folder layout, sidecar chains, and verifier setup.
3. **Run `free-check`.** Confirm lint passes, the oracle run passes every check, and the nop run fails.
4. **Run each route through the verifier.** If the task has a judgment check, or a check an agent could fail while its work looks right, script the routes an agent could take: yours, any other valid one, and each plausible wrong one. Run them with no model. Valid routes should pass, and each wrong route should fail the check meant for it. [Add a task](add-a-task.md#run-each-route-through-the-verifier) shows how.
5. **Trial it on the models you have access to.** Run the task in internet mode on your frontier plans (ideally both Claude Code and Codex). If you also have OpenRouter access, run the open models from [`job.yaml`](../runner/ethevals/job.yaml) too for the strongest evidence. If you do not have OpenRouter keys, that is fine. Maintainers and CI can run those checks.
6. **Read the trajectories before tuning.** Separate real failures in the agent's work from setup bugs, ambiguous instructions, or overly narrow checks. Fix the task when the failure is ours, then open the pull request with the evidence in its body, as [Add a task](add-a-task.md#open-the-pull-request) describes. See [Plan and run](../runner/README.md#plan-and-run) for runner commands and budgets.

## Optional map and resources

Use these as inspiration, not as a list you have to walk through.

### Areas of Ethereum

Rough use cases from [ethereum.org](https://ethereum.org/en/use-cases/) with blocks from the [Ethereum tech tree](https://gist.github.com/technophile-04/4d50f54a43fc1c407d6b6fe894596548):

- Financial tools (DEX and swaps, lending, vaults and staking, stablecoins, payments and payouts, oracles)
- Digital ownership and gaming (NFTs, onchain art and metadata, games and randomness)
- Organizations and identity (DAOs and voting, multisigs, ENS and identity, sign in with Ethereum, social)
- Novel uses (tokenized assets, prediction markets, restaking)
- AI agents (agent wallets, paying per call, agent registries)
- Science and public goods (grants, quadratic funding, DeSci, ReFi)
- UX and infra (smart contract wallets and account abstraction, indexing, bridges and L2s, mempool and MEV)

### Sources

Where developers learn and build:

- [Ethereum tech tree](https://gist.github.com/technophile-04/4d50f54a43fc1c407d6b6fe894596548) ([raw markdown](https://gist.github.com/technophile-04/4d50f54a43fc1c407d6b6fe894596548/raw/ethereum-tech-tree.md))
- [SpeedRunEthereum challenges](https://github.com/scaffold-eth/se-2-challenges) and [build prompts](https://speedrunethereum.com/build-prompts)
- [ETH Tech Tree](https://github.com/BuidlGuidl/eth-tech-tree-challenges) and [BuidlGuidl CTF](https://ctf.buidlguidl.com)
- [ethereum.org developer docs](https://ethereum.org/en/developers/docs/)

Libraries, skills, and audits where teams record real pitfalls:

- [wagmi](https://wagmi.sh), [viem](https://viem.sh), [Scaffold-ETH 2](https://github.com/scaffold-eth/scaffold-eth-2)
- [OpenZeppelin](https://github.com/OpenZeppelin/openzeppelin-contracts), [Solady](https://github.com/vectorized/solady), [Permit2](https://github.com/Uniswap/permit2)
- Pattern skills: [OpenZeppelin](https://github.com/OpenZeppelin/openzeppelin-skills), [Trail of Bits](https://github.com/trailofbits/skills), [Pashov Audit Group](https://github.com/pashov/skills), [Cyfrin](https://github.com/Cyfrin/solskill), [Uniswap](https://github.com/Uniswap/uniswap-ai), [Paul Berg](https://github.com/PaulRBerg/agent-skills)
- Audit reports and incidents: [Spearbit](https://github.com/spearbit/portfolio), [Trail of Bits](https://github.com/trailofbits/publications), [Pashov Audit Group](https://github.com/pashov/audits), [Rekt](https://rekt.news)

Background:

- [Anthropic's post on automating eval design](https://claude.dev/blog/automating-eval-design-and-hillclimbing/)
