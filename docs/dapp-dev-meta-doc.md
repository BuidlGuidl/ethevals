# dapp-dev meta doc: how we find and shape tasks

This doc is for the agent helping someone write dapp-development tasks for ETH Evals and the Ethereum Foundation's ethereum-benchmarks. It covers how we think about the territory, what a good task looks like to us, and how to start finding one. The details live behind the links.

We test agents that already build like senior developers. A task finds where they still fall short across the whole job of shipping an app: contracts, scripts and the frontend. Security is one part of that job.

## How we think about the territory

### The tech tree is the door

[The Ethereum tech tree](https://gist.github.com/technophile-04/4d50f54a43fc1c407d6b6fe894596548) takes a developer from junior to senior. Agents are already past most of it. They know an app needs a cron job, and they know how to deploy. What we take from the tech tree is its big blocks: DEX, lending, NFTs, DAOs, smart contract wallets and the rest. Those blocks are where you start. For each one you read how it is built today, mainly in apps live on Ethereum mainnet, and the task comes out of that reading.

### The map

Use cases are what the app is for, in the words of ethereum.org's [use cases](https://ethereum.org/en/use-cases/), with the tech tree's blocks in brackets:

- Financial tools (DEX and swaps, lending, vaults and staking, stablecoins, payments and payouts, oracles)
- Digital ownership and gaming (NFTs, onchain art and metadata, games and randomness)
- Organizations and identity (DAOs and voting, multisigs, ENS and identity, sign in with Ethereum, social)
- Novel uses (tokenized assets, prediction markets, restaking)
- AI agents (agent wallets, paying per call, agent registries)
- Science and public goods (grants, quadratic funding, DeSci, ReFi)
- UX and infra (smart contract wallets and account abstraction, indexing, bridges and L2s, mempool and MEV)

The last one takes its name from the tech tree, because ethereum.org has no use case for it. The list will extend as tasks arrive.

A task works in one or more parts of the app: the contracts, the scripts and the frontend.

The map is for looking around. A task can touch several use cases and parts of the app, and many tasks can sit in the same one. What matters is overlap. Before you write checks, read the README of each task already in [`tasks/`](../tasks/), and make sure your checks are mostly new.

### Two kinds of task

Each builder story gives a few quizzes and a build.

- A quiz goes to a bare model and has a fixed answer. It tests a concept, and the answer stays the same whichever library you use.
- A build gives an agent an environment and an instruction written as the builder's message. Hidden checks look at two things. Did the agent do the job, and did it do what a senior Ethereum app developer would do without being told?

## What a good task looks like

### A builder story with its own mechanics

A builder story is the app a developer would ask for, plus the mechanics that make it theirs. "A lending market" names a use case. The story adds what this team's market does differently.

The one finished example is [revenue payouts](../tasks/building/revenue-payouts/). Its story is an NFT team that splits its income by share, where the income arrives as ETH from the mint and as stablecoins from partners. Its README shows the instruction, what the instruction leaves out, and the checks.

### The instruction reads like a builder's message

Write the instruction as the message that builder would send. A real builder says what they want and why, plus the few things they would mention anyway, such as where the code goes or who will call it. That is usually enough for the checks to reach the work. The rest is the agent's call, and that is where the unsaid things live. If every agent would build something different, the instruction is too loose. If it lists every function and edge case, it has become a spec, and a spec only tests whether the agent can follow it.

### The bar is what a strong model misses

A good task is one that a strong current model gets wrong without being told, for a reason a senior developer would recognise. Only a trial shows that. An incident or a textbook shows that people got something wrong. That's a reason to try the idea, not proof that a model will miss it.

Keep these in mind while you shape a task:

- Would a reviewer on a real team block the merge without this check?
- Would a competent developer still get it wrong, where a senior one gets it right?
- Does more than one source teach this idea?
- Does it use today's tools and standards?

## How to start finding one

### Taste and judgment

Finding a task is a funnel with two filters. Reading turns up many ideas quickly, and most of them look fine. Taste is the first filter. It is the feel for a good task that the section above describes, and it rules out most ideas fast. What it leaves is a few good ideas it can't choose between. Judgment is the second filter. It weighs what each of those would teach us against what it costs in reading, trials and the reviewer's time, and it picks one. Taste without judgment gives a fine task too late. Judgment without taste gives a task on time that every model passes.

Judgment also sets how much you read. Read until you have a few ideas worth filtering, then stop. Hand reading to helpers when it saves time: two or three of them, each with one clear question and a short report to bring back. Keep it one level deep, so each helper does its own reading and reports to you. The taste stays with you, so read their reports and the code they point to before you choose.

### The steps

1. Pick a big block from the map that you can picture a builder asking for.
2. Read how it is built today:
   - Start with two or three apps live on Ethereum mainnet. That is where the most value sits and where the patterns are most tested. Read each app and its GitHub repo as a vertical slice: the contracts, and how the frontend and scripts use them. Take the patterns the best teams use and leave the code.
   - Follow what the apps raise into the libraries' source and comments, which show what their authors worry about, and into audit checklists and recent incidents. Go to them with a question from the apps.
   - Look hardest at what changed after a model's training, because memory can't carry it.
3. Write a few builder stories, two lines each: the story, and what it never mentions that a senior developer would handle. Let taste drop most of them and judgment pick one.
4. Write the quizzes and the build's instruction from that story.
5. Show the person you're working with the story, the quizzes, the build's instruction and the decisions behind them, including the stories you dropped and why. Agree on them before any trial.
6. Trial the build cheaply. Give the instruction to a strong agent in a plain project two or three times, and read what it built. Write the hidden checks around what it actually missed.
7. Build the task folder. Read [CONTEXT.md](../CONTEXT.md) for the words and [Add a task](add-a-task.md) for the folder.
8. Calibrate it with the runner, using your own keys in a `.env` at the repo root, passed with `uv run --env-file .env`. Round 1 is one trial each of `claude-code-opus-5.5`, `codex-gpt-6.1-sol` and `opencode-glm-5.3` in the internet mode. If GLM passes every check, the task is too easy. If the failures come from the task itself, such as a vague instruction or a check that accepts only one design, fix the task. Otherwise round 2 is a second trial each for Opus and GPT. [Plan and run](../runner/README.md#plan-and-run) has the commands and budgets.

## Sources

Where builders learn. Use these as doors.

- The Ethereum tech tree as one markdown file: [gist](https://gist.github.com/technophile-04/4d50f54a43fc1c407d6b6fe894596548), or the [raw file](https://gist.githubusercontent.com/technophile-04/4d50f54a43fc1c407d6b6fe894596548/raw/ethereum-tech-tree.md) for agents
- [SpeedRunEthereum challenges](https://github.com/scaffold-eth/se-2-challenges) and [build prompts](https://speedrunethereum.com/build-prompts)
- [ETH Tech Tree](https://github.com/BuidlGuidl/eth-tech-tree-challenges)
- [BuidlGuidl CTF](https://ctf.buidlguidl.com)

How experienced teams build:

- Apps live on Ethereum mainnet in the use case, and their GitHub repos
- [wagmi](https://wagmi.sh), [viem](https://viem.sh), [Scaffold-ETH 2](https://github.com/scaffold-eth/scaffold-eth-2)
- [OpenZeppelin](https://github.com/OpenZeppelin/openzeppelin-contracts), [Solady](https://github.com/vectorized/solady), [Permit2](https://github.com/Uniswap/permit2)
- [Pashov Audit Group's skills](https://github.com/pashov/skills)

What went wrong in the wild: [Rekt](https://rekt.news).

Background:

- [ethereum.org developer docs](https://ethereum.org/en/developers/docs/)
- [The dapp-development proposal](https://shiv-notes.notion.site/Dapp-development-discussion-3f9c3b5e527581529604dc8d4dc251b5)
- [Anthropic's post on automating eval design](https://claude.dev/blog/automating-eval-design-and-hillclimbing/)
