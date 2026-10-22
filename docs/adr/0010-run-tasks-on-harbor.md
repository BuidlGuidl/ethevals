---
status: accepted, amended by ADR-0011
---

# Run tasks on Harbor

ETH Evals runs on [Harbor](https://harborframework.com), locally, on CI, and for anyone who pulls our tasks from Hugging Face.
Each task is a Harbor task folder that its author writes directly, usually through the author's own agent.
Inspect, inspect_swe, and our own eval folder format leave the repo.
This ADR supersedes [ADR 0002](0002-run-evals-on-inspect.md) and [ADR 0008](0008-eval-spec-v2.md), and amends [ADR 0004](0004-evals-bring-their-own-services.md), [ADR 0005](0005-free-checks-on-pr-paid-runs-after-merge.md), and [ADR 0006](0006-direct-provider-keys-and-native-search.md).

We switched for four reasons:

- **Plans.** Inspect makes every model call from the host, so it can't bill a Claude or ChatGPT plan, and its maintainers have said that won't change. Harbor runs the unmodified CLI in the container with the plan's token.
- **What we publish is what we run.** The folders on Hugging Face are the folders the board runs, so an outside run and ours use the same task.
- **Agents write tasks.** Harbor's folder is a public format agents already know, and every task proves itself with Harbor's oracle and nop agents.
- **Codex gets current models.** ADR 0006 held Codex on GPT-5.5 because Inspect's bridge couldn't serve GPT-6's search endpoint.

## A task

| Path | Job |
| --- | --- |
| `task.toml` | Harbor's settings, plus our metadata: pillar, motivation, and modes |
| `instruction.md` | What the agent receives, written the way a real user would send it |
| `environment/` | The agent's container and any sidecars, such as a chain |
| `tests/` | `test.sh` and the checks it runs. It reaches the trial only when the verifier starts |
| `solution/` | `solve.sh`, which the oracle agent runs |

- **Conventions live in shared images and in the real tasks.** There's no template folder, and there's no chain by default. An author copies the task closest to the new one. The real tasks are run by the free check on every pull request, so they can't drift from the conventions.
- **The chain image** ships anvil behind the RPC filter, `ChainSetup`, forge-std, and a shared `foundry.toml` with `ffi` off.
  - The filter stays default-deny, as ADR 0008 set it. The agent can't call `anvil_*` or other chain controls.
  - Setup runs inside the chain sidecar. It writes `chain_context.json` for the agent and `private_chain_context.json` for the tests alone.
  - A fork takes its RPC URL from a secret that only anvil sees.
- **`test.sh` writes one record per check:** its name, pass or fail, and a one-line reason. The reward is 1 only when every check passes. Per-check numbers stay available for anyone who wants partial credit.
- **Forge is the first test tool with a helper.** A test function is one check, and its revert message is the reason. These ADR 0008 rules carry over:
  - the shared `compile` check
  - the `<Contract>.setUp` and `<Contract>.constructor` checks
  - remappings scoped to each agent project
  - `--no-storage-caching` on forks

  Any other tool can write the same records.
- **Where the verifier runs.** Tasks without a chain use Harbor's separate verifier. Tasks with a chain run the verifier in the agent's container, because a separate verifier starts after the chain has stopped and only sees copied files.
- **Criteria replace rubrics.** RewardKit's judge answers each criteria question as its own check. The judge is Opus 5.5, paid by API key. It reads the trajectory and the files the task lists, and every result records which judge ran.
- **Modes.** The vanilla mode runs through our own Harbor agent, which makes one plain API call with no tools. The internet mode is the agent as it ships. The skills mode adds the repo's skills pack.
- **The agent must not know it's tested.** Lint rejects eval words in the instruction and in the files the agent can see, as ADR 0008 did.

## Running

- **One job config holds the board-wide settings:** agents, models, pinned CLI versions, the Harbor version, and the time limit. No task sets its own time limit.
- **Billing:**
  - Claude Code runs on BuidlGuidl's Claude plan, and Codex on BuidlGuidl's ChatGPT plan, locally and on CI. The Codex login is rotated weekly.
  - OpenCode runs Kimi and GLM on OpenRouter keys.
  - The judge and the vanilla agent use API keys.
  - On CI, each plan runs one trial at a time.
- **Cost.** Every trial records the API-price cost of its model calls, whether a plan or a key paid, and the result records which one paid. The board shows that cost for every trial.
- **The budget gate stays.** A paid run plans only the missing trials, and API-key spend has to fit the budget before anything starts.
- **The board shows a count.** A trial passes only if every check passes, and the board shows how many trials passed, such as 3 of 5. Each trial's trajectory and verifier output go to release assets, and the run drawer links the trajectory.
- **Old results leave the board.** The 160 results from the Inspect runner are dropped, and every task runs again on Harbor.

## Pull requests

- **The free check needs no secrets and no model.** It runs lint, an oracle run that must pass every check, and a nop run that must fail.
- **A fork task's oracle and nop runs need the RPC secret.** They run in the fork check, which a maintainer starts by hand, as ADR 0008 set up.
- **The lint keeps ADR 0004's rule** that a task's containers get no privileged mode and no host mounts.

## Publishing

- **Every push to `main` uploads the task folders to `buidlguidl/ethevals-test`,** along with a `registry.json` and an `eval.yaml` that names `evaluation_framework: harbor`. The dataset card carries the `rl-environment` and `harbor` tags.
- **The folders run with a plain `harbor run --repo`** and no ETH Evals code, because the images are prebuilt on ghcr.
- **No canary string.** We want models to train on the public tasks, and measuring stays the main purpose. The cost: a model trained on our tasks can score from memory, and the board can't tell. A held-out set is the fix if that happens.

## Known gaps

We take Harbor's isolation as it ships, and come back to each gap when it causes a problem.

- The plan token or API key sits in the agent's container, where the agent can read it.
- Nothing freezes the agent before the verifier. In a chain task, a process the agent left running can still act while the tests run.
- A chain task's verifier shares the agent's container, rather than sitting on a network the agent can't reach.
- There's no cost cap per trial, except Claude Code's own budget flag.
- Criteria read a trajectory that the CLI writes inside the container, not a record made on the host.
- Anthropic's terms are unclear on running a plan from CI. OpenAI's CI guide says not to use a ChatGPT login for public repositories. We run both plans on CI anyway, and stop if a provider objects or the runs break.
- ADR 0008's cheatcode gap still applies: an agent's contract can call the cheatcode address while the tests run.

## Considered options

- **Keep Inspect, and export Harbor folders for outsiders.** That keeps the host-side key, the freeze, and the separate scorer. But the board couldn't use plans, and the published folders would be a second path that the board never runs.
- **Compile our own folder format into Harbor tasks.** It enforces more, but agents would have to learn and debug through a translation layer.
- **Use the separate verifier for every task.** It's Harbor's coming default, but it stops the chain before the tests can read it.
- **Run RewardKit's judge on a plan.** That sends plan credentials through a third-party library, which Anthropic's terms rule out.

## Changes to earlier ADRs

- **ADR 0002 is superseded.**
- **ADR 0008 is superseded.** The rules this ADR lists as carrying over still hold.
- **ADR 0004 is amended.** Tasks write their own compose files. The lint still rejects privileged containers and host mounts.
- **ADR 0005 is amended.** The reference and untouched passes become the oracle and nop runs. Paid runs still start only after merge.
- **ADR 0006 is amended.** Claude Code and Codex run on plans, and Codex is no longer held on GPT-5.5. Each CLI uses its own search, and OpenCode keeps Exa.
- **ADR 0001 and ADR 0009 still hold,** with this ADR's words: tasks, trials, and agents on models.
