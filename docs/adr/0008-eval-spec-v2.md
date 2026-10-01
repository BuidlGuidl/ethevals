---
status: accepted
---

# Eval spec v2: the files declare the eval, and Foundry runs every step

An eval folder has no `type`. The files it holds decide how it runs and how it is scored, and Solidity with Foundry is the one language for setup, tests, and reference solutions.
Authors write what Solidity developers already write, and any scorer works with any chain.
This ADR supersedes [ADR 0003](0003-eval-folder-is-a-declaration.md) and [ADR 0007](0007-rubrics-for-any-eval.md), and amends [ADR 0004](0004-evals-bring-their-own-services.md) and [ADR 0005](0005-free-checks-on-pr-paid-runs-after-merge.md).

## The folder

The folder stays data. Authors write no runner code, and tools read every eval without running it.

| Path | Job | Reaches the agent |
| --- | --- | --- |
| `eval.yaml` | `prompt`, `motivation`, `modes`, and optional `chain` and `choices`. Other keys fail validation | the prompt |
| `workspace/` | the agent's starting files | as shipped |
| `setup/` | `setup.s.sol` and the contracts only setup deploys | no |
| `scorer/` | one or more of `target.yaml`, `tests/*.t.sol`, and `rubric.md` | no |
| `solution/` | the reference solution | no |

- Only `scorer/` is required. A `chain` requires `setup/setup.s.sol`, and `setup/` requires a `chain`. `vanilla` needs an eval with no `chain`, no `workspace/`, and no `tests/`, because a bare model has nowhere to put work.
- The agent sees the prompt, `workspace/`, and the eval's services. With a chain, it also sees `chain.json` and the filtered RPC. In the skills mode, it has the skills pack. The runner adds nothing else.
- The agent must not know it is tested. `ethevals validate` rejects eval words in the prompt and workspace files, and `ethevals check` rejects them in `chain.json`.
- A target's check takes its `name`. A test's check is its function name, and tests add one `compile` check. A rubric's check is its `##` heading. Names are unique across the eval and carry no prefix. A reverting `setUp` or constructor gives one check named `<Contract>.setUp` or `<Contract>.constructor`.
- `target.yaml` keeps Inspect's sample fields, so the Hugging Face dataset loads into Inspect with no mapping. The dataset holds the evals that declare `vanilla` and are graded by a target alone.

## Foundry for setup, tests, and solutions

- `chain` is absent, `anvil`, or `{fork: <network>, block: <number>}`, where the network is `mainnet` or `base`.
- Setup is a forge script that inherits `ChainSetup`, which adds `fund`, `chainRecord`, and `privateRecord`. It runs in the chain container on the unfiltered RPC. The agent gets `chain.json`. The tests get `chain.json` and `private.json`.
- Tests are Forge tests. They import the agent's code by its workspace path and read the finished chain with `vm.createSelectFork`. Before grading, the runner stops the agent and mines one block. Forge compiles only the tests and what they import.
- The scorer picks the test tool from the file names in `scorer/tests/`, through the `RUNNERS` table in `scorers.py`. Forge claims `*.t.sol`, and a file no test tool claims is a helper. `compile` is one check per eval, shared by every test tool. Adding a test tool takes three changes: the tool in the scorer's image, one `RUNNERS` entry, and a docs section.
- The reference solution overlays `solution/` on the workspace, and `solution/solution.s.sol` runs in the scorer container against the filtered RPC. Every eval with tests or a chain ships one. A solution that uses a library ships as one file made with `forge flatten`.
- The agent image ships no Solidity libraries. The agent's `foundry.toml` and libraries are its own. The scorer uses its own config and maps each agent project's libraries only for files in that project.
- The scorer runs on the chain image, which ships forge, forge-std, and `ChainSetup`. No image ships a Solidity compiler: every container has internet, and Forge installs the version each pragma asks for. A failed compiler download is an error that retries, never a failed `compile` check. A pragma that no released compiler satisfies fails `compile`.

We picked Forge tests because every Solidity developer writes them, Hardhat 3 runs the same dialect, and `forge test --json` gives one result per test. One test tool grades a build, a transaction, and a fix.

## Containers

- The agent, the chain, and any author services share the `work` network. The scorer and the chain share `grading`. Each service has its own internet network, so the agent can't reach the scorer.
- The RPC filter stays default-deny. It allows the standard `eth_` methods, including the filter family. A CI test fails on any anvil method that the allowlist file doesn't classify.

## Forks

- The fork's RPC URL is a repository secret per network, `MAINNET_RPC_URL` or `BASE_RPC_URL`, passed only to anvil in the chain container. The filter and the runner replace the URL with `<fork rpc>` in RPC replies and command output.
- Setup moves tokens from a holder with three `vm.rpc` calls on the unfiltered anvil: `anvil_impersonateAccount`, `eth_sendTransaction` from the holder, and `anvil_stopImpersonatingAccount`. Nothing broadcasts from the holder. The filter refuses `eth_sendTransaction`, so the agent can't send as the holder.
- Grading runs `forge test --no-storage-caching`, so Forge's fork cache can't carry chain state from one epoch to the next.
- The free check on a pull request has no secrets. For a fork eval it validates the folder and skips the reference and untouched passes.
- A maintainer reads the PR, then dispatches the fork check workflow with the PR number and the SHA of the commit they read. If the PR head has moved, the run fails. Otherwise it runs both passes with the secret and no model and posts a `fork check` status on that commit. The eval merges only after that status passes. The trigger is manual because the secret reaches setup code that the PR wrote.

## Rubrics, limits, and paid runs

- Any eval can have a rubric, alone or with other scorers. The grader reads the transcript, with the agent's compiled source in front when the tests compiled it.
- Rubric evidence has no size cap. The runner trims it only to fit the grader model's context window, and the plan's rubric reserve follows that window.
- Every epoch has a 2-hour time limit and a $20 cost limit. No eval or scorer sets its own. An epoch that reaches the time limit is scored on what the agent left.
- An epoch is one agent, or one bare model in the vanilla mode, on one eval in one mode at one effort, executed once. The epoch number counts repeats.
- Paid CI runs one GitHub job per epoch. A `plan` job lists the missing epochs, a matrix runs each one, and `publish` folds the artifacts into one results commit.

## Changes to earlier ADRs

- ADR 0003 is superseded. `type`, check scripts, shebang setup scripts, `RPC_URL` and `PUBLIC_RPC_URL`, and `scorer/solution/` with `run.sh` are gone. Its rejected options still hold.
- ADR 0004 is amended. The stock compose file follows `chain`, not a type. Author services join `work` instead of `private`. Setup is a forge script, and check scripts are gone. The scorer's config allows reads of `chain.json` and `private.json`. A `chain` key exists, because a fork needs settings that an author's compose file can't hold: the secret URL, the memory, and the timeouts.
- ADR 0005 is amended. The free check's passes cover targets and tests, since check scripts are gone. The reference solution lives in `solution/` and is required wherever tests or a chain exist. Fork evals add the fork check, and paid runs use one job per epoch.
- ADR 0007 is superseded. A rubric can be an eval's only scorer, every rubric reads the transcript, the evidence cap is gone, and one time limit replaces the working, total, and scoring limits.

## Considered options

- A scorer bundle per `type`: it locked scorers to a type, and an eval that builds a contract and also needs a chain fit no bundle.
- Check scripts in Bash or Python: a second dialect, a JSON output contract, and more tools in the chain image.
- A runner-owned `foundry.toml` with OpenZeppelin preinstalled: it chose the agent's library and compiler settings, which are part of the work under test.
- Remappings in plain order: an agent's `remappings.txt` line could replace forge-std's `Test.sol` and make every assertion pass. Remappings scoped to each agent folder block that.
- A prefix blocklist for RPC methods: anvil's chain controls sit in five namespaces, and a missed one is silent.
- A label to start the fork check: a `labeled` event on a pull request from a fork gets no secrets.

## Known gaps

- An agent's contract runs inside Forge's test environment, so it can call the cheatcode address and fake what a test reads with `vm.mockCall` or `vm.store`. This is allowed for now and watched in transcripts. If it shows up, a walk over the `forge test -vvvv` traces can fail the epoch when anything but the test contract calls the cheatcode address.
- A fork eval's full check waits on a maintainer.
- The free check can't exercise a rubric, so for a rubric-only eval the reviewer reading `rubric.md` is the only guard.
